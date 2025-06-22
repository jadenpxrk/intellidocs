`# IntelliDocs Setup Guide

Complete setup instructions for the IntelliDocs GitHub App - an automated documentation generator that creates docs for your code changes.

## Prerequisites

- Python 3.8 or higher
- GitHub account with repository admin access
- ngrok (for local development)

## Step 1: Clone and Install Dependencies

```bash
git clone <your-repo-url>
cd intellidocs

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Create GitHub App

1. Go to GitHub Settings → Developer settings → GitHub Apps
2. Click "New GitHub App"
3. Fill in the details:
   - **App name**: `IntelliDocs` (or your preferred name)
   - **Homepage URL**: `https://github.com/your-username/intellidocs`
   - **Webhook URL**: `https://your-ngrok-url.ngrok.io/webhook` (we'll set this up next)
   - **Webhook secret**: Generate a random string (save this!)
4. Set permissions:
   - **Repository permissions**:
     - Contents: Read & Write
     - Metadata: Read
     - Pull requests: Read
     - Commit statuses: Write
   - **Subscribe to events**:
     - Push
5. Create the app and note down the **App ID**
6. Generate and download the **Private Key** (save as `app_private_key.pem`)

## Step 3: Setup ngrok for Local Development

```bash
# Install ngrok (macOS)
brew install ngrok

# Authenticate ngrok (get token from https://ngrok.com/)
ngrok authtoken YOUR_NGROK_TOKEN

# Start ngrok tunnel
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`) and update your GitHub App's webhook URL to `https://abc123.ngrok.io/webhook`.

## Step 4: Configure Environment Variables

Create a `.env` file in the project root:

```bash
# GitHub App Configuration
GITHUB_APP_ID=your_app_id_here
GITHUB_PRIVATE_KEY_PATH=app_private_key.pem
WEBHOOK_SECRET=your_webhook_secret_here

# Target repository for documentation output
DOCS_REPO_OWNER=your_github_username
DOCS_REPO_NAME=your-project-docs
```

## Step 5: Install GitHub App on Repository

1. Go to your GitHub App settings
2. Click "Install App"
3. Choose the repository you want to monitor
4. Grant the necessary permissions

## Step 6: Run the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Start the server
python main.py
```

The server will start on `http://localhost:8000`. You should see:

```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

## Step 7: Test the Setup

1. Make a commit to your monitored repository:

   ```bash
   echo "# Test" >> test.py
   git add test.py
   git commit -m "Test IntelliDocs webhook"
   git push
   ```

2. Check the server logs for webhook activity:

   ```
   📨 Webhook received!
   ✅ Signature verified!
   📋 Event type: push
   🚀 Processing push event...
   ```

3. The app will automatically create a separate documentation repository and generate docs for your code files.

## Troubleshooting

### Webhook Not Receiving Events

- Check that ngrok is running and the URL is correct
- Verify the webhook URL in your GitHub App settings
- Ensure the webhook secret matches your `.env` file

### Authentication Errors

- Verify your GitHub App ID is correct
- Check that the private key file exists and is readable
- Ensure your app is installed on the target repository

### Permission Errors

- Verify your GitHub App has the required permissions
- Check that the app is installed on both source and docs repositories
- Ensure the docs repository exists or can be created

### Server Errors

- Check the server logs for detailed error messages
- Verify all dependencies are installed in the virtual environment
- Ensure Python 3.8+ is being used

## Test Mode

For testing without GitHub authentication, use:

```bash
python main_bypass.py
```

This bypasses GitHub API calls and shows what would happen.

## Production Deployment

For production deployment (e.g., on Fly.io), update the webhook URL to your production domain and ensure all environment variables are properly set.

## File Structure

```
intellidocs/
├── main.py                 # Main FastAPI application
├── main_bypass.py         # Test version (bypasses GitHub auth)
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
├── app_private_key.pem   # GitHub App private key (download this)
├── src/
│   ├── auth.py           # GitHub App authentication
│   ├── webhook.py        # Webhook event handling
│   ├── git_operations.py # Git repository operations
│   └── docs_generator.py # Documentation generation
└── README.md
```

## API Endpoints

- `GET /` - Health check endpoint
- `GET /health` - Application health status
- `POST /webhook` - GitHub webhook endpoint

---

Once setup is complete, the app will automatically generate documentation for any code changes pushed to your monitored repositories!
