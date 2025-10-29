import boto3
import json
import os
from dotenv import load_dotenv

load_dotenv()

# init bedrock client
bedrock = boto3.client(
    service_name = 'bedrock-runtime',
    region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
)

def test_bedrock():
    '''test bedrock api call'''

    user_message = "Say hello and tell me you're ready to analyze League of Legends data!"

    conversation = [
        {
            "role": "user",
            "content": [{"text": user_message}]
        }
    ]

    try:
        response = bedrock.converse(
            modelId = 'anthropic.claude-3-haiku-20240307-v1:0',
            messages = conversation,
            inferenceConfig={"maxTokens": 200, "temperature": 0.5}
        )

        response_text = response["output"]["message"]["content"][0]["text"]

        print("Bedrock Connection Successful!")
        print(f"\nAI Response: \n{response_text}")
        return True
    
    except Exception as e:
        print(f"Error: {e}")
        return False
    
if __name__ == "__main__":
    test_bedrock()
    