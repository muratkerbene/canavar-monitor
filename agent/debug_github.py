import json
import os
import requests

def debug_update():
    github_raw_url = "https://raw.githubusercontent.com/muratkerbene/canavar-monitor/main"
    print(f"Checking URL: {github_raw_url}/version.txt")
    
    try:
        r = requests.get(f"{github_raw_url}/version.txt", timeout=10)
        print("Status code:", r.status_code)
        print("Content:", repr(r.text))
        
        r2 = requests.get(f"{github_raw_url}/agent/agent.py", timeout=10)
        print("Agent Status code:", r2.status_code)
        
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    debug_update()
