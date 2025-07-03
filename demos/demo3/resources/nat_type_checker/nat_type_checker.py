import socket
import requests
import stun
import time

def get_public_ip():
    try:
        response = requests.get('https://api.ipify.org?format=json')
        response.raise_for_status()
        return response.json()['ip']
    except requests.RequestException as e:
        print(f"Error fetching public IP: {e}")
        return None

def get_stun_info(retries=3, delay=2):
    for attempt in range(retries):
        try:
            nat_type, external_ip, external_port = stun.get_ip_info()
            if external_ip is not None:
                return nat_type, external_ip, external_port
        except Exception as e:
            print(f"Error fetching STUN info (attempt {attempt + 1}): {e}")
        time.sleep(delay)
    return None, None, None

def check_cone_nat():

    print("\nRunning... This will take a few seconds\n")

    try:
        nat_type, external_ip, external_port = get_stun_info()
        public_ip = get_public_ip()

        if public_ip is None:
            print("Could not determine public IP")
            return

        if external_ip is None:
            print("Could not determine STUN server IP")
            return

        print(f"Public IP: {public_ip}")
        print(f"STUN server IP: {external_ip}")

        if public_ip == external_ip:
            print("You have a Cone NAT")
        else:
            print("You do not have a Cone NAT")
    except Exception as e:
        print(f"Error checking NAT type: {e}")

if __name__ == "__main__":
    check_cone_nat()