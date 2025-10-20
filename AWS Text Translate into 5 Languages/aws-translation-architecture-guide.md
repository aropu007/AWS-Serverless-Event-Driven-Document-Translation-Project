# AWS Event-Driven Document Translation Architecture - Complete Guide

## Architecture Overview

This solution uses:
- **S3 Buckets**: Storage for input/output files
- **Lambda Functions**: Processing logic
- **API Gateway**: REST API for frontend
- **Amazon Textract**: Extract text from PDFs/images
- **Amazon Comprehend**: Summarization
- **Amazon Translate**: Multi-language translation
- **EventBridge/S3 Events**: Trigger processing

## Architecture Flow

```
User → HTML Frontend → API Gateway → Lambda (Upload Handler)
                                          ↓
                                      S3 Input Bucket
                                          ↓
                                   S3 Event Trigger
                                          ↓
                          Lambda (Processing Function)
                                          ↓
                          Textract → Comprehend → Translate
                                          ↓
                                   S3 Output Bucket
                                          ↓
                          HTML Frontend (Download)
```

---

## STEP 1: Create S3 Buckets

### 1.1 Create Input Bucket
1. Go to AWS Console → **S3**
2. Click **Create bucket**
3. **Bucket name**: `translate-abduropu-input`
4. **Region**: Choose your preferred region (e.g., us-east-1)
5. **Block Public Access settings**: Keep all boxes CHECKED
6. **Bucket Versioning**: Enable (optional)
7. Click **Create bucket**

### 1.2 Create Output Bucket
1. Click **Create bucket** again
2. **Bucket name**: `translate-abduropu-output`
3. **Region**: Same as input bucket
4. **Block Public Access settings**: Keep all boxes CHECKED
5. Click **Create bucket**

### 1.3 Configure CORS for Input Bucket
1. Go to `translate-abduropu-input` bucket
2. Click **Permissions** tab
3. Scroll to **Cross-origin resource sharing (CORS)**
4. Click **Edit** and paste:

```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
        "AllowedOrigins": ["*"],
        "ExposeHeaders": ["ETag"]
    }
]
```

5. Click **Save changes**

### 1.4 Configure CORS for Output Bucket
1. Go to `translate-abduropu-output` bucket
2. Click **Permissions** tab
3. Add same CORS configuration as above

---

## STEP 2: Create IAM Roles

### 2.1 Create Lambda Execution Role for Processing Function

1. Go to AWS Console → **IAM**
2. Click **Roles** → **Create role**
3. **Trusted entity type**: AWS service
4. **Use case**: Lambda
5. Click **Next**
6. Search and attach these policies:
   - `AmazonS3FullAccess`
   - `AmazonTextractFullAccess`
   - `TranslateFullAccess`
   - `ComprehendFullAccess`
   - `CloudWatchLogsFullAccess`
7. Click **Next**
8. **Role name**: `LambdaTranslationProcessingRole`
9. Click **Create role**

### 2.2 Create Lambda Execution Role for API Function

1. Click **Create role** again
2. **Trusted entity type**: AWS service
3. **Use case**: Lambda
4. Click **Next**
5. Attach these policies:
   - `AmazonS3FullAccess`
   - `CloudWatchLogsFullAccess`
6. Click **Next**
7. **Role name**: `LambdaAPIRole`
8. Click **Create role**

---

## STEP 3: Create Lambda Functions

### 3.1 Create Processing Lambda Function

1. Go to AWS Console → **Lambda**
2. Click **Create function**
3. Choose **Author from scratch**
4. **Function name**: `DocumentTranslationProcessor`
5. **Runtime**: Python 3.12
6. **Architecture**: x86_64
7. **Permissions**: 
   - Choose **Use an existing role**
   - Select `LambdaTranslationProcessingRole`
8. Click **Create function**

9. In the **Code** tab, replace the default code with:

```python
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
```

10. Click **Deploy**

11. **Configure timeout**:
    - Scroll down to **Configuration** tab
    - Click **General configuration** → **Edit**
    - Set **Timeout** to `5 minutes`
    - Set **Memory** to `512 MB`
    - Click **Save**

### 3.2 Create API Lambda Function

1. Click **Create function**
2. **Function name**: `DocumentUploadAPI`
3. **Runtime**: Python 3.12
4. **Permissions**: Use existing role `LambdaAPIRole`
5. Click **Create function**

6. Replace code with:

```python
import json
import boto3
import base64
import uuid
from datetime import datetime

s3 = boto3.client('s3')
INPUT_BUCKET = 'translate-abduropu-input'  # Your input bucket name

def lambda_handler(event, context):
    try:
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
        
        # Parse request
        body = json.loads(event['body'])
        
        if event['path'] == '/upload':
            return handle_upload(body)
        elif event['path'] == '/list':
            return handle_list()
        else:
            return {
                'statusCode': 404,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Not found'})
            }
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }

def handle_upload(body):
    """Handle file upload"""
    file_content = body['fileContent']
    file_name = body['fileName']
    target_language = body['targetLanguage']
    
    # Decode base64 file content
    file_data = base64.b64decode(file_content.split(',')[1] if ',' in file_content else file_content)
    
    # Generate unique key
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_key = f"{timestamp}_{uuid.uuid4().hex[:8]}_{file_name}"
    
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
    
    return {
        'statusCode': 200,
        'headers': {'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({
            'message': 'File uploaded successfully',
            'key': unique_key
        })
    }

def handle_list():
    """List translated files from output bucket"""
    OUTPUT_BUCKET = 'translate-abduropu-output'  # Your output bucket name
    
    response = s3.list_objects_v2(
        Bucket=OUTPUT_BUCKET,
        Prefix='translated/'
    )
    
    files = []
    if 'Contents' in response:
        for obj in response['Contents']:
            # Generate presigned URL for download
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': OUTPUT_BUCKET, 'Key': obj['Key']},
                ExpiresIn=3600
            )
            
            files.append({
                'key': obj['Key'],
                'size': obj['Size'],
                'lastModified': obj['LastModified'].isoformat(),
                'downloadUrl': url
            })
    
    return {
        'statusCode': 200,
        'headers': {'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({'files': files})
    }
```

7. Click **Deploy**

---

## STEP 4: Configure S3 Event Trigger

1. Go to **Lambda** → `DocumentTranslationProcessor` function
2. Click **Add trigger**
3. Select **S3**
4. **Bucket**: Select `translate-abduropu-input`
5. **Event type**: Select `All object create events`
6. **Prefix**: Leave empty (to process all files)
7. **Suffix**: Leave empty
8. Check the acknowledgment box
9. Click **Add**

---

## STEP 5: Create API Gateway

### 5.1 Create REST API

1. Go to AWS Console → **API Gateway**
2. Click **Create API**
3. Choose **REST API** (not private)
4. Click **Build**
5. **API name**: `DocumentTranslationAPI`
6. **Endpoint Type**: Regional
7. Click **Create API**

### 5.2 Create Resources and Methods

#### Create /upload resource
1. Click **Actions** → **Create Resource**
2. **Resource Name**: `upload`
3. Check **Enable API Gateway CORS**
4. Click **Create Resource**

5. With `/upload` selected, click **Actions** → **Create Method**
6. Select **POST** from dropdown → Click checkmark
7. **Integration type**: Lambda Function
8. Check **Use Lambda Proxy integration**
9. **Lambda Function**: `DocumentUploadAPI`
10. Click **Save** → **OK**

#### Create /list resource
1. Click on `/` (root)
2. Click **Actions** → **Create Resource**
3. **Resource Name**: `list`
4. Check **Enable API Gateway CORS**
5. Click **Create Resource**

6. With `/list` selected, click **Actions** → **Create Method**
7. Select **GET** from dropdown → Click checkmark
8. **Integration type**: Lambda Function
9. Check **Use Lambda Proxy integration**
10. **Lambda Function**: `DocumentUploadAPI`
11. Click **Save** → **OK**

### 5.3 Deploy API

1. Click **Actions** → **Deploy API**
2. **Deployment stage**: [New Stage]
3. **Stage name**: `prod`
4. Click **Deploy**
5. **Copy the Invoke URL** (e.g., `https://xxxxxx.execute-api.us-east-1.amazonaws.com/prod`)

---

## STEP 6: Create HTML Frontend

Now I'll create the HTML frontend with file upload and download capabilities.

Save this as `index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document Translation Service</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            text-align: center;
            color: white;
            margin-bottom: 40px;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }

        .main-content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 40px;
        }

        @media (max-width: 968px) {
            .main-content {
                grid-template-columns: 1fr;
            }
        }

        .card {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }

        .card h2 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.8em;
        }

        .upload-area {
            border: 3px dashed #667eea;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 20px;
        }

        .upload-area:hover {
            background-color: #f8f9ff;
            border-color: #764ba2;
        }

        .upload-area.dragover {
            background-color: #e8ebff;
            border-color: #764ba2;
        }

        .upload-icon {
            font-size: 3em;
            margin-bottom: 10px;
        }

        input[type="file"] {
            display: none;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
        }

        select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
            transition: border-color 0.3s;
        }

        select:focus {
            outline: none;
            border-color: #667eea;
        }

        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-size: 1.1em;
            cursor: pointer;
            width: 100%;
            transition: transform 0.2s, box-shadow 0.2s;
            font-weight: 600;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }

        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }

        .file-info {
            background: #f8f9ff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }

        .file-info.show {
            display: block;
        }

        .file-info p {
            margin: 5px 0;
            color: #666;
        }

        .status-message {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }

        .status-message.show {
            display: block;
        }

        .status-message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .status-message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        .status-message.info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }

        .translated-files {
            max-height: 500px;
            overflow-y: auto;
        }

        .file-item {
            background: #f8f9ff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: transform 0.2s;
        }

        .file-item:hover {
            transform: translateX(5px);
            background: #e8ebff;
        }

        .file-details {
            flex: 1;
        }

        .file-name {
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }

        .file-meta {
            font-size: 0.9em;
            color: #666;
        }

        .download-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            transition: background 0.3s;
        }

        .download-btn:hover {
            background: #218838;
        }

        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
            display: none;
        }

        .spinner.show {
            display: block;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .language-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-top: 10px;
        }

        .language-chip {
            background: #e8ebff;
            padding: 8px;
            border-radius: 5px;
            text-align: center;
            font-size: 0.9em;
            color: #667eea;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌍 Document Translation Service</h1>
            <p>Upload, Translate, and Download - Powered by AWS</p>
        </div>

        <div class="main-content">
            <!-- Upload Section -->
            <div class="card">
                <h2>📤 Upload Document</h2>
                
                <div id="uploadArea" class="upload-area">
                    <div class="upload-icon">📄</div>
                    <p><strong>Click to upload</strong> or drag and drop</p>
                    <p style="color: #999; font-size: 0.9em;">PDF, DOC, or TXT files</p>
                </div>
                
                <input type="file" id="fileInput" accept=".pdf,.doc,.docx,.txt">
                
                <div id="fileInfo" class="file-info">
                    <p><strong>Selected File:</strong> <span id="fileName"></span></p>
                    <p><strong>Size:</strong> <span id="fileSize"></span></p>
                </div>

                <div class="form-group">
                    <label for="languageSelect">Select Target Language</label>
                    <select id="languageSelect">
                        <option value="es">Spanish (Español)</option>
                        <option value="fr">French (Français)</option>
                        <option value="ar">Arabic (العربية)</option>
                        <option value="ru">Russian (Русский)</option>
                        <option value="bn">Bengali (বাংলা)</option>
                    </select>
                </div>

                <div class="language-grid">
                    <div class="language-chip">🇪🇸 Spanish</div>
                    <div class="language-chip">🇫🇷 French</div>
                    <div class="language-chip">🇸🇦 Arabic</div>
                    <div class="language-chip">🇷🇺 Russian</div>
                    <div class="language-chip">🇧🇩 Bengali</div>
                </div>

                <div id="statusMessage" class="status-message"></div>
                <div id="uploadSpinner" class="spinner"></div>

                <button id="uploadBtn" class="btn" disabled>Upload & Translate</button>
            </div>

            <!-- Download Section -->
            <div class="card">
                <h2>📥 Translated Documents</h2>
                
                <button id="refreshBtn" class="btn" style="margin-bottom: 20px;">
                    🔄 Refresh List
                </button>

                <div id="downloadSpinner" class="spinner"></div>
                
                <div id="translatedFiles" class="translated-files">
                    <p style="text-align: center; color: #999;">No translated files yet</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Configuration - UPDATE THIS WITH YOUR API GATEWAY URL
        const API_URL = 'https://YOUR-API-ID.execute-api.YOUR-REGION.amazonaws.com/prod';
        
        // DOM Elements
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const fileInfo = document.getElementById('fileInfo');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const uploadBtn = document.getElementById('uploadBtn');
        const languageSelect = document.getElementById('languageSelect');
        const statusMessage = document.getElementById('statusMessage');
        const uploadSpinner = document.getElementById('uploadSpinner');
        const downloadSpinner = document.getElementById('downloadSpinner');
        const translatedFiles = document.getElementById('translatedFiles');
        const refreshBtn = document.getElementById('refreshBtn');

        let selectedFile = null;

        // Upload Area Click
        uploadArea.addEventListener('click', () => fileInput.click());

        // Drag and Drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFileSelect(files[0]);
            }
        });

        // File Input Change
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFileSelect(e.target.files[0]);
            }
        });

        // Handle File Selection
        function handleFileSelect(file) {
            selectedFile = file;
            fileName.textContent = file.name;
            fileSize.textContent = formatFileSize(file.size);
            fileInfo.classList.add('show');
            uploadBtn.disabled = false;
        }

        // Format File Size
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }

        // Show Status Message
        function showStatus(message, type) {
            statusMessage.textContent = message;
            statusMessage.className = `status-message show ${type}`;
            setTimeout(() => {
                statusMessage.classList.remove('show');
            }, 5000);
        }

        // Upload Button Click
        uploadBtn.addEventListener('click', async () => {
            if (!selectedFile) return;

            uploadBtn.disabled = true;
            uploadSpinner.classList.add('show');
            showStatus('Uploading and processing...', 'info');

            try {
                // Read file as base64
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const fileContent = e.target.result;

                    // Send to API
                    const response = await fetch(`${API_URL}/upload`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            fileContent: fileContent,
                            fileName: selectedFile.name,
                            targetLanguage: languageSelect.value
                        })
                    });

                    const result = await response.json();

                    if (response.ok) {
                        showStatus('✅ File uploaded successfully! Translation in progress...', 'success');
                        
                        // Reset form
                        selectedFile = null;
                        fileInput.value = '';
                        fileInfo.classList.remove('show');
                        
                        // Refresh file list after a delay
                        setTimeout(() => loadTranslatedFiles(), 3000);
                    } else {
                        showStatus('❌ Upload failed: ' + result.error, 'error');
                    }

                    uploadBtn.disabled = false;
                    uploadSpinner.classList.remove('show');
                };

                reader.readAsDataURL(selectedFile);

            } catch (error) {
                console.error('Error:', error);
                showStatus('❌ Error uploading file: ' + error.message, 'error');
                uploadBtn.disabled = false;
                uploadSpinner.classList.remove('show');
            }
        });

        // Load Translated Files
        async function loadTranslatedFiles() {
            downloadSpinner.classList.add('show');

            try {
                const response = await fetch(`${API_URL}/list`);
                const result = await response.json();

                if (response.ok && result.files.length > 0) {
                    translatedFiles.innerHTML = result.files.map(file => `
                        <div class="file-item">
                            <div class="file-details">
                                <div class="file-name">${file.key.split('/').pop()}</div>
                                <div class="file-meta">
                                    Size: ${formatFileSize(file.size)} | 
                                    Modified: ${new Date(file.lastModified).toLocaleString()}
                                </div>
                            </div>
                            <button class="download-btn" onclick="downloadFile('${file.downloadUrl}', '${file.key.split('/').pop()}')">
                                ⬇️ Download
                            </button>
                        </div>
                    `).join('');
                } else {
                    translatedFiles.innerHTML = '<p style="text-align: center; color: #999;">No translated files yet</p>';
                }

            } catch (error) {
                console.error('Error loading files:', error);
                translatedFiles.innerHTML = '<p style="text-align: center; color: #dc3545;">Error loading files</p>';
            }

            downloadSpinner.classList.remove('show');
        }

        // Download File
        function downloadFile(url, filename) {
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }

        // Refresh Button
        refreshBtn.addEventListener('click', loadTranslatedFiles);

        // Initial Load
        loadTranslatedFiles();
        
        // Auto-refresh every 30 seconds
        setInterval(loadTranslatedFiles, 30000);
    </script>
</body>
</html>
```

---

## STEP 7: Host HTML Frontend on S3 Static Website

Instead of opening the HTML file locally, you can host it on S3 as a static website for professional deployment.

### 7.1 Create S3 Bucket for Website

1. Go to AWS Console → **S3**
2. Click **Create bucket**
3. **Bucket name**: `translate-abduropu-website` (must be globally unique)
4. **Region**: Same as your other buckets
5. **Block Public Access settings**: 
   - ⚠️ **UNCHECK** "Block all public access"
   - Check the acknowledgment box (we need this for public website access)
6. Click **Create bucket**

### 7.2 Enable Static Website Hosting

1. Click on your `translate-abduropu-website` bucket
2. Go to **Properties** tab
3. Scroll down to **Static website hosting**
4. Click **Edit**
5. Select **Enable**
6. **Hosting type**: Static website hosting
7. **Index document**: `index.html`
8. **Error document**: `index.html` (optional)
9. Click **Save changes**
10. **Note the Website endpoint URL** (e.g., `http://translate-abduropu-website.s3-website-us-east-1.amazonaws.com`)

### 7.3 Update HTML with API Gateway URL

1. Open `index.html` file in a text editor
2. Find line 404: `const API_URL = 'https://YOUR-API-ID.execute-api.YOUR-REGION.amazonaws.com/prod';`
3. Replace with your actual API Gateway URL from Step 5
4. Save the file

**Example:**
```javascript
// Before
const API_URL = 'https://YOUR-API-ID.execute-api.YOUR-REGION.amazonaws.com/prod';

// After (replace with your actual URL)
const API_URL = 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod';
```

### 7.4 Upload HTML to S3

1. Go to your `translate-abduropu-website` bucket
2. Click **Upload**
3. Click **Add files**
4. Select your updated `index.html` file
5. Click **Upload**
6. Wait for upload to complete

### 7.5 Make HTML File Public

**Option A: Using Bucket Policy (Recommended)**

1. Go to **Permissions** tab of your website bucket
2. Scroll to **Bucket policy**
3. Click **Edit**
4. Paste this policy (replace `translate-abduropu-website` with your actual bucket name):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::translate-abduropu-website/*"
        }
    ]
}
```

5. Click **Save changes**

**Option B: Using Object ACL**

1. Click on `index.html` in your bucket
2. Go to **Permissions** tab
3. Click **Edit** under Object Ownership (if needed)
4. Enable ACLs
5. Go back to object, click **Actions** → **Make public using ACL**
6. Confirm

### 7.6 Access Your Website

1. Go to **Properties** tab of your website bucket
2. Scroll to **Static website hosting**
3. Copy the **Bucket website endpoint** URL
4. Open the URL in your browser

**Your website is now live!** 🎉

Example URL format:
```
http://translate-abduropu-website.s3-website-us-east-1.amazonaws.com
```

### 7.7 Test the Website

1. Open your S3 website URL in a browser
2. Try uploading a test file
3. Select a target language
4. Click "Upload & Translate"
5. Wait 30-60 seconds
6. Click "Refresh List"
7. Download your translated file

---

## STEP 8 (OPTIONAL): Add HTTPS with CloudFront

For production use, add HTTPS using CloudFront CDN.

### 8.1 Create CloudFront Distribution

1. Go to AWS Console → **CloudFront**
2. Click **Create distribution**
3. **Origin domain**: Select your S3 website endpoint (not the bucket, but the website endpoint)
   - Format: `translate-abduropu-website.s3-website-us-east-1.amazonaws.com`
4. **Protocol**: HTTP only (S3 website endpoints don't support HTTPS)
5. **Viewer protocol policy**: Redirect HTTP to HTTPS
6. **Allowed HTTP methods**: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE
7. **Cache policy**: CachingOptimized
8. **Origin request policy**: CORS-S3Origin
9. **Default root object**: `index.html`
10. Click **Create distribution**
11. Wait 5-15 minutes for deployment
12. **Copy the Distribution domain name** (e.g., `d1234abcd.cloudfront.net`)

### 8.2 Access via CloudFront (HTTPS)

Your website is now available at:
```
https://d1234abcd.cloudfront.net
```

This provides:
- ✅ HTTPS encryption
- ✅ Global CDN (faster loading)
- ✅ Custom domain support (optional)

### 8.3 (Optional) Add Custom Domain

If you own a domain (e.g., `translate.yourdomain.com`):

1. Go to **AWS Certificate Manager** (ACM)
2. Request a public certificate for your domain
3. Validate domain ownership
4. Go back to CloudFront distribution
5. Click **Edit**
6. Add your domain to **Alternate domain names (CNAMEs)**
7. Select your ACM certificate
8. Update your DNS (Route 53 or external) to point to CloudFront

---

## STEP 9: Update Lambda Functions with Bucket Names

*Note: This was previously Step 8, now renumbered*

## STEP 10: Update Lambda Functions with Bucket Names

### 10.1 Update DocumentTranslationProcessor
1. Go to Lambda → `DocumentTranslationProcessor`
2. Find line: `OUTPUT_BUCKET = 'translate-abduropu-output'`
3. This is already set to your bucket name
4. Click **Deploy**

### 10.2 Update DocumentUploadAPI
1. Go to Lambda → `DocumentUploadAPI`
2. Find line: `INPUT_BUCKET = 'translate-abduropu-input'`
3. This is already set to your bucket name
4. Find line: `OUTPUT_BUCKET = 'translate-abduropu-output'` (in handle_list function)
5. This is already set to your bucket name
6. Click **Deploy**

---

## STEP 11: Test the System

### 11.1 Open HTML Frontend

**Option 1: Local Testing**
1. Open `index.html` directly in your web browser

**Option 2: S3 Static Website (Recommended)**
1. Go to your S3 website URL (from Step 7.6)
2. Example: `http://translate-abduropu-website.s3-website-us-east-1.amazonaws.com`

You should see the Document Translation Service interface.

### 11.2 Upload a Test File
1. Click the upload area or drag a file
2. Select a PDF, DOC, or TXT file
3. Choose a target language (e.g., Spanish)
4. Click **Upload & Translate**
5. Wait for the success message

### 11.3 Monitor Processing
1. Go to AWS Console → **Lambda** → `DocumentTranslationProcessor`
2. Click **Monitor** → **View CloudWatch logs**
3. Check the latest log stream for processing status

### 11.4 Check Output
1. After 30-60 seconds (depending on file size), click **Refresh List**
2. You should see your translated file appear
3. Click **Download** to get the translated text file

---

## Troubleshooting

### Issue: Upload fails with CORS error
**Solution**: 
- Verify CORS is enabled on API Gateway methods
- Check S3 bucket CORS configuration
- Ensure browser isn't blocking requests

### Issue: Translation not happening
**Solution**:
- Check S3 event trigger is configured on input bucket
- Verify Lambda execution role has all required permissions
- Check CloudWatch logs for errors

### Issue: Textract fails on PDF
**Solution**:
- Ensure PDF is not encrypted
- Check file size (Textract has limits)
- Verify Textract service is available in your region

### Issue: Download returns 403 error
**Solution**:
- Check output bucket permissions
- Verify presigned URL generation in Lambda
- Ensure bucket CORS allows GET requests

---

## Cost Optimization Tips

1. **Use S3 Lifecycle Policies**: Auto-delete files after 30 days
2. **Set Lambda Memory**: Adjust based on actual usage
3. **Use S3 Intelligent-Tiering**: For cost-effective storage
4. **Monitor AWS Costs**: Use AWS Cost Explorer

---

## Architecture Diagram

### Complete Architecture with S3 Static Website Hosting

```
┌──────────────────────┐
│   User's Browser     │
└──────────┬───────────┘
           │
           │ Access Website
           ▼
┌──────────────────────┐     ┌──────────────────┐
│  S3 Static Website   │ OR  │  CloudFront CDN  │ (Optional HTTPS)
│  (HTML Frontend)     │     │  (HTTPS/Custom)  │
└──────────┬───────────┘     └────────┬─────────┘
           │                          │
           └──────────┬───────────────┘
                      │
                      │ API Calls (HTTPS)
                      ▼
           ┌─────────────────┐
           │  API Gateway    │
           │  (REST API)     │
           └────────┬────────┘
                    │
                    │ Invoke Lambda
                    ▼
           ┌──────────────────┐
           │ Lambda Function  │
           │  (Upload API)    │
           └────────┬─────────┘
                    │
                    │ PUT Object + Metadata
                    ▼
           ┌──────────────────────┐
           │   S3 Input Bucket    │
           │ translate-abduropu   │
           │      -input          │
           └──────────┬───────────┘
                      │
                      │ S3 Event Trigger
                      ▼
           ┌──────────────────────┐
           │  Lambda Processor    │
           │  (Main Processing)   │
           └──────────┬───────────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
         ▼            ▼            ▼
┌─────────────┐ ┌──────────┐ ┌──────────┐
│  Textract   │ │Comprehend│ │Translate │
│  (Extract)  │ │(Summary) │ │(5 langs) │
└─────────────┘ └──────────┘ └──────────┘
                      │
                      │ Save Translation
                      ▼
           ┌──────────────────────┐
           │  S3 Output Bucket    │
           │ translate-abduropu   │
           │      -output         │
           └──────────┬───────────┘
                      │
                      │ Presigned URL
                      ▼
           ┌──────────────────────┐
           │   User Download      │
           │   (via Frontend)     │
           └──────────────────────┘
```

### Simplified Flow

```
┌─────────────┐
│   Browser   │
│  (HTML UI)  │
└──────┬──────┘
       │
       │ HTTPS
       ▼
┌─────────────────┐
│  API Gateway    │
│  (REST API)     │
└────────┬────────┘
         │
         │ Invoke
         ▼
┌──────────────────┐
│ Lambda Function  │
│  (Upload API)    │
└────────┬─────────┘
         │
         │ PUT Object
         ▼
┌──────────────────┐
│   S3 Bucket      │
│ (Translate Input)│
└────────┬─────────┘
         │
         │ S3 Event
         ▼
┌──────────────────┐
│ Lambda Function  │
│  (Processor)     │
└────────┬─────────┘
         │
         ├──────────────┐
         │              │
         ▼              ▼
┌─────────────┐  ┌──────────────┐
│  Textract   │  │  Comprehend  │
│  (Extract)  │  │ (Summarize)  │
└─────────────┘  └──────────────┘
         │
         ▼
┌──────────────────┐
│    Translate     │
│  (Multi-lang)    │
└────────┬─────────┘
         │
         │ PUT Object
         ▼
┌──────────────────┐
│   S3 Bucket      │
│(Translate Output)│
└──────────────────┘
         │
         │ Download
         ▼
┌──────────────────┐
│     Browser      │
└──────────────────┘
```

---

## Next Steps & Enhancements

1. **Add Authentication**: Implement Amazon Cognito for user authentication
2. **Email Notifications**: Use SNS to notify users when translation is complete
3. **Progress Tracking**: Store translation status in DynamoDB
4. **Batch Processing**: Handle multiple file uploads
5. **Custom Vocabulary**: Use Amazon Translate custom terminologies
6. **File Size Optimization**: Implement chunking for large documents
7. **Error Handling**: Add retry logic and dead letter queues

---

## Security Best Practices

1. ✅ **IAM Least Privilege**: Use minimal required permissions
2. ✅ **Encryption**: Enable S3 bucket encryption
3. ✅ **API Authentication**: Add API keys or Cognito auth
4. ✅ **VPC**: Consider placing Lambda in VPC for sensitive data
5. ✅ **Logging**: Enable CloudTrail for audit logs
6. ✅ **Secrets Management**: Use AWS Secrets Manager for sensitive configs

---

## Supported Languages

| Language | Code | Flag |
|----------|------|------|
| Spanish  | es   | 🇪🇸  |
| French   | fr   | 🇫🇷  |
| Arabic   | ar   | 🇸🇦  |
| Russian  | ru   | 🇷🇺  |
| Bengali  | bn   | 🇧🇩  |

---

## AWS Services Used

- **Amazon S3**: File storage
- **AWS Lambda**: Serverless compute
- **Amazon API Gateway**: REST API
- **Amazon Textract**: Text extraction from PDFs
- **Amazon Comprehend**: Text summarization
- **Amazon Translate**: Multi-language translation
- **Amazon CloudWatch**: Logging and monitoring
- **AWS IAM**: Access management

---

## Support & Resources

- [AWS Documentation](https://docs.aws.amazon.com/)
- [Amazon Translate Docs](https://docs.aws.amazon.com/translate/)
- [Amazon Textract Docs](https://docs.aws.amazon.com/textract/)
- [Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)

---

**🎉 Congratulations! Your Event-Driven Translation Architecture is Complete!**

This guide provides a fully functional, serverless document translation system using AWS services. Upload documents, select your target language, and download translated text files—all through a beautiful web interface!
