import json
import boto3
import os
import logging
from datetime import datetime
from decimal import Decimal
from botocore.exceptions import ClientError

promptTemplate = """\n\nHuman: You are a summarisation assistant. Your task is to summarise product reviews given to you as a list. Within this list, there are individual product reviews in an array.
Create a JSON document with the following fields:
reviews_summary - A summary of these reviews in less than 250 words
overall_sentiment - The overall sentiment of the reviews
sentiment_confidence - How confident you are about the sentiment of the reviews on a scale of 0 to 1
reviews_positive - The percent of positive reviews
reviews_neutral - The percent of neutral reviews
reviews_negative - The percent of negative reviews
action_items - A list of action items from the reviews
Your output should be raw JSON - do not include any sentences or additional text outside of the JSON object.
Here is the list of reviews that I want you to summarise:
{list}
\n\nAssistant:"""

logger = logging.getLogger(__name__)

def lambda_handler(event, context):
    # Read the reviews for one product from S3
    print("Reading from S3")
    s3 = boto3.resource("s3")
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    file = event["Records"][0]["s3"]["object"]["key"]
    object = s3.Object(bucket, file)
    data = json.loads(object.get()["Body"].read())
    print("Read from S3")
    
    # Add the reviews to the LLM prompt
    prompt = promptTemplate.format(list=data["reviews"])
    
    # Invoke the LLM
    print("Invoking bedrock")
    bedrock = boto3.client("bedrock-runtime", region_name="us-west-2") # Bedrock is not currently available in all regions
    # Invoke Claude 3 with the text prompt
    model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    try:
        response = bedrock.invoke_model(
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ],
                "max_tokens": 4000,
                "temperature": 0,
                "top_p": 0.8,
                "top_k": 250
            }),
            contentType="application/json",
            accept="application/json",
            modelId=model_id
        )
        print("Response received from bedrock")
        print ("response from bedrock", response)
        
        # Process and print the response
        result = json.loads(response.get("body").read())
        input_tokens = result["usage"]["input_tokens"]
        output_tokens = result["usage"]["output_tokens"]
        output_list = result.get("content", [])

        print("Invocation details:")
        print(f"- The input length is {input_tokens} tokens.")
        print(f"- The output length is {output_tokens} tokens.")
        print ("output_list ", output_list)
        print(f"- The model returned {len(output_list)} response(s):")
        
        
        analysis = json.loads(output_list[0].get("text"))
        print ("response_body", analysis)
        # Claude sometimes adds extra text, remove everything that isn't within {}
        #response_body = response_body[response_body.find('{'):response_body.find('}') + 1]
        #analysis = json.loads(response_body)
        
        # Store the analysis in DynamoDB
        print("Saving to DynamoDB")
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(os.environ["DYNAMODB_TABLE"])
        table.put_item(
            Item={
                'product': data["product"],
                'date': datetime.today().strftime('%d-%m-%Y'),
                'create_time': datetime.today().strftime('%d-%m-%YT%H:%M:%S'),
                'reviews_summary': analysis["reviews_summary"],
                'overall_sentiment': analysis["overall_sentiment"],
                'sentiment_confidence': str(analysis["sentiment_confidence"]),
                'reviews_positive': analysis["reviews_positive"],
                'reviews_negative': analysis["reviews_negative"],
                'reviews_neutral': analysis["reviews_neutral"],
                'action_items': json.dumps(analysis["action_items"]),
            }
        )
        print("Saved to DynamoDB")
        
        return {
            'statusCode': 200,
            'body': json.dumps('Successfully analysed customer reviews')
        }
    except ClientError as err:
        print(
            "Couldn't invoke Claude 3 Sonnet. Here's why: %s: %s",
            err.response["Error"]["Code"],
            err.response["Error"]["Message"],
        )
        logger.error(
            "Couldn't invoke Claude 3 Sonnet. Here's why: %s: %s",
            err.response["Error"]["Code"],
            err.response["Error"]["Message"],
        )
        raise
