import re
import sys

def update_api_keys(file_path, access_keys, openai_key, google_key, deepseek_key):
    with open(file_path, 'r') as f:
        content = f.read()

    content = re.sub(r'^ACCESS_API_KEYS=.*$', f'ACCESS_API_KEYS={access_keys}', content, flags=re.M)
    content = re.sub(r'^OPENAI_API_KEY=.*$', f'OPENAI_API_KEY={openai_key}', content, flags=re.M)
    content = re.sub(r'^GOOGLE_API_KEY=.*$', f'GOOGLE_API_KEY={google_key}', content, flags=re.M)
    content = re.sub(r'^DEEPSEEK_API_KEY=.*$', f'DEEPSEEK_API_KEY={deepseek_key}', content, flags=re.M)

    with open(file_path, 'w') as f:  
        f.write(content)

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: python update_api_keys.py <access_keys> <openai_key> <google_key> <deepseek_key>")
        sys.exit(1)

    access_keys = sys.argv[1] 
    openai_key = sys.argv[2]
    google_key = sys.argv[3]
    deepseek_key = sys.argv[4]

    update_api_keys('.env', access_keys, openai_key, google_key, deepseek_key)
