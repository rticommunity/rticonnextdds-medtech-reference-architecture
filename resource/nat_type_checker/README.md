# NAT Type Checker

This script checks if you have a Cone NAT by comparing your public IP address
with the IP address seen by a STUN server.

## Requirements

- Python 3.x
- python3-pip
- `requests` library
- `pystun3` library

## Installation

To install the required libraries, run the following commands:

```sh
pip install requests pystun3
```

## Usage

Run the script using python3:

```sh
python3 nat_type_checker.py
```

The script will output whether you have a Cone NAT or not.

## Script Explanation

The script performs the following steps:

1. Fetches your public IP address using the `requests` library and the `ipify` service.
2. Uses the `pystun3` library to get the IP address seen by a STUN server.
3. Compares the two IP addresses to determine if you have a Cone NAT.

If the public IP address matches the IP address seen by the STUN server, it
indicates that you have a Cone NAT.

## Example Output

```plaintext
Running... This will take a few seconds

Public IP: 203.0.113.1
STUN server IP: 203.0.113.1
You have a Cone NAT
```

If the IP addresses do not match, the script will output:

```plaintext
Running... This will take a few seconds

Public IP: 203.0.113.1
STUN server IP: 198.51.100.1
You do not have a Cone NAT
```
