import subprocess
import os
import sys
from pathlib import Path

MODULES = {
    "operating-room": [
        "Arm", 
        "ArmController", 
        "Orchestrator", 
        "PatientMonitor", 
        "PatientSensor"
    ],
    "record-playback": [
        "RecordingService", 
        "ReplayService"
    ],
    "remote-teleoperation": [
        "RsActive", 
        "RsCloud", 
        "RsPassive"
    ]
}

DOMAINS = ["Domain0", "Domain1"]

def run_command(cmd, description=""):
    """Run a shell command and handle errors."""
    if description:
        print(f"Running: {description}")
    
    try:
        print(f"$ {cmd}")
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Error output: {e.stderr}")
        return False

def setup_ca():
    """Generate self-signed CA certificate."""
    print("=== Setting up Certificate Authority ===")
    
    # Ensure ca/private directory exists
    ca_dir = Path("ca")
    ca_private_dir = ca_dir / "private"
    ca_private_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = ("openssl req -nodes -x509 -days 1825 -text -sha256 "
           "-newkey ec -pkeyopt ec_paramgen_curve:prime256v1 "
           f"-keyout {ca_private_dir/"CaPrivateKey.pem"} "
           f"-out {ca_dir/"CaIdentity.pem"} "
           f"-config {ca_dir/"Ca.cnf"}")
    
    return run_command(cmd, "Generating self-signed CA certificate")

def setup_identities():
    """Generate private keys and identity certificates for all participants."""
    print("\n=== Generating Participant Certificates ===")
    
    success = True
    
    ca_dir = Path("ca")
    ca = ca_dir / "CaIdentity.pem"
    ca_key = ca_dir / "private" / "CaPrivateKey.pem"

    if not ca.exists() or not ca_key.exists():
        print("Error: CA certificate or private key not found. Please set up the CA first.")
        return False
    
    for module, participants in MODULES.items():
        print(f"\nProcessing for module: {module}")
        
        # Ensure directory exists        
        for participant in participants:
            print(f"  Generating certificate for: {participant}")
            
            # Ensure participant directory exists
            participant_dir = Path("identities") / module / participant
            participant_dir.mkdir(parents=True, exist_ok=True)

            if not participant_dir.is_dir():
                print(f"Error: Directory {participant_dir} does not exist.")
                success = False
                break
            
            base_path = participant_dir / participant
            
            # Generate private key and certificate signing request
            csr_cmd = (f"openssl req -nodes -new -newkey rsa:2048 "
                      f"-config \"{base_path}.cnf\" "
                      f"-keyout \"{base_path}PrivateKey.pem\" "
                      f"-out \"{base_path}.csr\"")
            
            if not run_command(csr_cmd, f"Generating CSR for {participant}"):
                success = False
                continue
            
            # Sign the certificate
            cert_cmd = (f"openssl x509 -req -days 730 -text "
                       f"-CA {ca} "
                       f"-CAkey {ca_key} "
                       f"-in \"{base_path}.csr\" "
                       f"-out \"{base_path}Identity.pem\"")
            
            if not run_command(cert_cmd, f"Signing certificate for {participant}"):
                success = False
        
        if not success:
            break
    
    return success

def sign_permission_files():
    """Sign permissions XML files."""
    print("\n=== Signing Permission XML Files ===")
    
    success = True

    ca_dir = Path("ca")
    ca = ca_dir / "CaIdentity.pem"
    ca_key = ca_dir / "private" / "CaPrivateKey.pem"

    for module, participants in MODULES.items():
        print(f"\nProcessing for module: {module}")

        # Ensure module directory exists
        module_dir = Path("xml") / module

        if not module_dir.is_dir():
            print(f"Error: Directory {module_dir} does not exist.")
            success = False
            break

        for participant in participants:
            permission_xml = module_dir / f"Permissions{participant}.xml"
            signed_permission = module_dir / "signed" / f"SignedPermissions{participant}.p7s"

            # Ensure permission XML file exists
            if not permission_xml.exists():
                print(f"Error: XML file {permission_xml} does not exist.")
                success = False

            # Ensure signed directory exists
            signed_permission.parent.mkdir(parents=True, exist_ok=True)

            sign_cmd = (f"openssl smime -sign "
                   f"-in \"{permission_xml}\" "
                   f"-text "
                   f"-out \"{signed_permission}\" "
                   f"-signer {ca} "
                   f"-inkey {ca_key}")
        
            if not run_command(sign_cmd, f"Signing {permission_xml}"):
                success = False
    
    return success

def sign_governance_files():
    """Sign governance XML files."""
    print("\n=== Signing Governance XML Files ===")
    
    success = True

    ca_dir = Path("ca")
    ca = ca_dir / "CaIdentity.pem"
    ca_key = ca_dir / "private" / "CaPrivateKey.pem"

    for module in MODULES.keys():
        print(f"\nProcessing for module: {module}")

        # Ensure module directory exists
        module_dir = Path("xml") / module

        if not module_dir.is_dir():
            print(f"Error: Directory {module_dir} does not exist.")
            success = False
            break

        governance_xml = module_dir / "Governance.xml"
        signed_governance = module_dir / "signed" / "SignedGovernance.p7s"

        # Ensure governance XML file exists
        if not governance_xml.exists():
            print(f"Error: XML file {governance_xml} does not exist.")
            success = False

        # Ensure signed directory exists
        signed_governance.parent.mkdir(parents=True, exist_ok=True)

        sign_cmd = (f"openssl smime -sign "
               f"-in \"{governance_xml}\" "
               f"-text "
               f"-out \"{signed_governance}\" "
               f"-signer {ca} "
               f"-inkey {ca_key}")
    
        if not run_command(sign_cmd, f"Signing {governance_xml}"):
            success = False
    
    return success

def cleanup_temp_files():
    """Remove temporary certificate signing request files."""
    print("\n=== Cleaning up temporary files ===")
    
    try:
        # Use Path.glob to find and remove all .csr files
        identities_dir = Path("identities")
        for csr_file in identities_dir.rglob("*.csr"):
            csr_file.unlink()
            print(f"Removed: {csr_file}")
        return True
    except Exception as e:
        print(f"Error during cleanup: {e}")
        return False

def main():
    """Main function to run the security setup process."""
    print("RTI Connext DDS Security Setup")
    print("=" * 40)
    
    # Change to the script's directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Check if required files exist
    ca_config = Path("ca/Ca.cnf")
    if not ca_config.exists():
        print(f"Error: {ca_config} not found. Please ensure the CA configuration file exists.")
        sys.exit(1)
    
    success = True
    
    # Step 1: Set up Certificate Authority
    if not setup_ca():
        print("Failed to set up Certificate Authority")
        success = False
    
    # Step 2: Generate participant certificates
    if success and not setup_identities():
        print("Failed to generate participant certificates")
        success = False
    
    # Step 3: Sign XML files
    if success and not sign_xml_files():
        print("Failed to sign XML files")
        success = False
    
    # Step 4: Clean up temporary files
    if success:
        cleanup_temp_files()
    
    if success:
        print("\n✓ Security setup completed successfully!")
    else:
        print("\n✗ Security setup completed with errors!")
        sys.exit(1)

if __name__ == "__main__":
    main()

