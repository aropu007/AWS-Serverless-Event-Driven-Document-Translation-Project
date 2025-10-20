import json
import boto3
import os
from urllib.parse import unquote_plus

s3 = boto3.client('s3')
textract = boto3.client('textract')
translate = boto3.client('translate')
comprehend = boto3.client('comprehend')

OUTPUT_BUCKET = 'translate-abduropu-output'  # Your output bucket name

def lambda_handler(event, context):
    try:
        # Parse S3 event
        record = event['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        
        print(f"Processing file: {key} from bucket: {bucket}")
        
        # Parse metadata from object tags or filename
        # Expected format: filename_LANGUAGE.pdf or use object metadata
        response = s3.head_object(Bucket=bucket, Key=key)
        metadata = response.get('Metadata', {})
        target_language = metadata.get('target-language', 'es')  # Default to Spanish
        
        print(f"Target language: {target_language}")
        
        # Step 1: Extract text from document
        extracted_text = extract_text(bucket, key)
        print(f"Extracted {len(extracted_text)} characters")
        
        # Step 2: Summarize text using Comprehend
        summary = summarize_text(extracted_text)
        print(f"Summary created: {len(summary)} characters")
        
        # Step 3: Translate summary
        translated_text = translate_text(summary, target_language)
        print(f"Translation complete")
        
        # Step 4: Save to output bucket
        output_key = f"translated/{os.path.splitext(os.path.basename(key))[0]}_{target_language}.txt"
        s3.put_object(
            Bucket=OUTPUT_BUCKET,
            Key=output_key,
            Body=translated_text.encode('utf-8'),
            ContentType='text/plain',
            Metadata={
                'original-file': key,
                'target-language': target_language,
                'source-language': 'en'
            }
        )
        
        print(f"Output saved to: {output_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Translation completed successfully',
                'output_file': output_key
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def extract_text(bucket, key):
    """Extract text from PDF/image using Textract or direct S3 read for text files"""
    file_extension = os.path.splitext(key)[1].lower()
    
    if file_extension in ['.txt']:
        # For text files, read directly
        response = s3.get_object(Bucket=bucket, Key=key)
        return response['Body'].read().decode('utf-8')
    
    elif file_extension in ['.pdf', '.png', '.jpg', '.jpeg']:
        # For PDFs and images, use Textract
        response = textract.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key
                }
            }
        )
        
        # Extract text from blocks
        text = ''
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                text += block['Text'] + '\n'
        
        return text
    
    else:
        raise ValueError(f"Unsupported file type: {file_extension}")

def summarize_text(text):
    """Summarize text using Amazon Comprehend (for short texts) or simple extraction"""
    # Comprehend has text length limits, so we'll use a simple approach
    # For production, you might want to use Amazon Bedrock or chunking strategies
    
    # If text is too long, truncate to first 5000 characters for translation
    if len(text) > 5000:
        # Take first 2500 and last 2500 characters as a simple summary
        summary = text[:2500] + "\n...\n" + text[-2500:]
        return summary
    
    return text

def translate_text(text, target_language_code):
    """Translate text using Amazon Translate"""
    # Language code mapping
    language_map = {
        'spanish': 'es',
        'russian': 'ru',
        'bengali': 'bn',
        'french': 'fr',
        'arabic': 'ar',
        'es': 'es',
        'ru': 'ru',
        'bn': 'bn',
        'fr': 'fr',
        'ar': 'ar'
    }
    
    target_code = language_map.get(target_language_code.lower(), target_language_code)
    
    # Amazon Translate has a 10k character limit per request
    # For longer texts, we need to chunk
    max_length = 9000
    translated_chunks = []
    
    for i in range(0, len(text), max_length):
        chunk = text[i:i + max_length]
        
        response = translate.translate_text(
            Text=chunk,
            SourceLanguageCode='en',
            TargetLanguageCode=target_code
        )
        
        translated_chunks.append(response['TranslatedText'])
    
    return ''.join(translated_chunks)