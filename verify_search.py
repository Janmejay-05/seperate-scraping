import requests
import json

def verify_search():
    url = "http://127.0.0.1:8000/api/search"
    payload = {
        "query": "sugar",
        "pincode": "380015",
        "max_results": 2,
        "headful": True 
    }
    
    print(f"Sending search request to {url}...")
    try:
        response = requests.post(url, json=payload, timeout=60)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Total Results: {len(data.get('all_results', []))}")
            print("Results by Platform:")
            print(json.dumps(data.get('by_platform', {}), indent=2))
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    verify_search()
