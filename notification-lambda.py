import boto3
from boto3.dynamodb.conditions import Key
import os
from datetime import datetime, timedelta

def lambda_handler(event, context):
    # Get entries from the previous day from DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ["DYNAMODB_TABLE"])
    yesterday = (datetime.today() - timedelta(days=1)).strftime('%d-%m-%Y')
    
    response = table.query(KeyConditionExpression=Key("date").eq(yesterday))
    entries = response["Items"]
    
    # Only continue if there are entries from yesterday
    if len(entries) == 0:
        print("No entries for yesterday")
        return

    # Convert the data to CSV format
    csv = ""
    keys = entries[0].keys()
    for key in keys:
        csv += key + ","
    csv += "\n"

    for entry in entries:
        for key in keys:
            value = str(entry[key])
            # Replace any double quotes with single quotes
            value = value.replace("\"", "'")
            # Surround the value with double quotes in case it contains any commas
            csv += "\"" + value + "\","
        csv += "\n"

    # Upload the CSV to S3
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(os.environ["S3_BUCKET"])
    bucket.put_object(Key=yesterday + ".csv", Body=csv)
    
    # Generate a presigned url for the object
    client = boto3.client('s3')
    url = client.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': os.environ["S3_BUCKET"],
            'Key': yesterday + ".csv"
        },
        ExpiresIn=86400 # 24 hours
        )
        
    # Send an email via SNS
    sns = boto3.resource('sns')
    topic = sns.Topic(os.environ["SNS_TOPIC"])
    topic.publish(Subject="Product Review Analysis", Message="The report for yesterday is ready. " + url)
