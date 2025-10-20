import json
import boto3
import base64
import uuid
from datetime import datetime

s3 = boto3.client('s3')

# ⚠️ UPDATE THESE WITH YOUR ACTUAL BUCKET NAMES ⚠️
INPUT_BUCKET = 'translate-abduropu-input'
OUTPUT_BUCKET = 'translate-abduropu-output'

def lambda_handler(event, context):
    try:
        print(f"Event received: {json.dumps(event)}")
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS'
                },
                'body': ''
            }
        
        # Route based on path
        path = event.get('path', '')
        print(f"Path: {path}")
        
        if path == '/upload' or path.endswith('/upload'):
            body = json.loads(event['body'])
            return handle_upload(body)
        elif path == '/list' or path.endswith('/list'):
            return handle_list()
        else:
            print(f"Unknown path: {path}")
            return {
                'statusCode': 404,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': f'Not found: {path}'})
            }
            
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }

def handle_upload(body):
    """Handle file upload"""
    try:
        print("Handling upload...")
        file_content = body['fileContent']
        file_name = body['fileName']
        target_language = body['targetLanguage']
        
        print(f"File: {file_name}, Language: {target_language}")
        
        # Decode base64 file content
        if ',' in file_content:
            file_data = base64.b64decode(file_content.split(',')[1])
        else:
            file_data = base64.b64decode(file_content)
        
        # Generate unique key
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_key = f"{timestamp}_{uuid.uuid4().hex[:8]}_{file_name}"
        
        print(f"Uploading to: {INPUT_BUCKET}/{unique_key}")
        
        # Upload to S3 with metadata
        s3.put_object(
            Bucket=INPUT_BUCKET,
            Key=unique_key,
            Body=file_data,
            Metadata={
                'target-language': target_language,
                'original-filename': file_name
            }
        )
        
        print("Upload successful!")
        
        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'message': 'File uploaded successfully',
                'key': unique_key
            })
        }
    except Exception as e:
        print(f"Error in handle_upload: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

def handle_list():
    """List translated files from output bucket"""
    try:
        print(f"Listing files from bucket: {OUTPUT_BUCKET}")
        
        # List all objects with the translated/ prefix
        response = s3.list_objects_v2(
            Bucket=OUTPUT_BUCKET,
            Prefix='translated/'
        )
        
        print(f"S3 Response: {json.dumps(response, default=str)}")
        
        files = []
        if 'Contents' in response:
            print(f"Found {len(response['Contents'])} files")
            for obj in response['Contents']:
                # Skip the folder itself
                if obj['Key'] == 'translated/':
                    continue
                    
                try:
                    # Generate presigned URL for download
                    url = s3.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': OUTPUT_BUCKET, 'Key': obj['Key']},
                        ExpiresIn=3600  # 1 hour
                    )
                    
                    files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'lastModified': obj['LastModified'].isoformat(),
                        'downloadUrl': url
                    })
                    print(f"Added file: {obj['Key']}")
                except Exception as e:
                    print(f"Error processing file {obj['Key']}: {str(e)}")
        else:
            print("No files found in bucket")
        
        print(f"Returning {len(files)} files")
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'files': files})
        }
    except Exception as e:
        print(f"Error in handle_list: {str(e)}")
        import traceback
        traceback.print_exc()
        raise