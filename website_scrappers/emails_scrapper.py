import asyncio
import aiohttp
from typing import List, Dict, Any
from datetime import datetime
from colorama import Fore, Style, init
from threading import Lock
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import base64
import email
from bs4 import BeautifulSoup
import pickle
import json
import re
init(autoreset=True)

print_lock = Lock()

def safe_print(message: str):
    with print_lock:
        print(message)

class EmailScraper:
    def __init__(self, max_concurrent: int = 5):
        self.source_name = "Gmail"
        self.source_url = "https://gmail.com"
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        self.service = self.get_gmail_service()

    def get_gmail_service(self):
        """Get Gmail API service instance"""
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return build('gmail', 'v1', credentials=creds)

    def get_email_content(self, msg):
        """Extract email content from message"""
        if msg.get('payload').get('body').get('data'):
            data = msg.get('payload').get('body').get('data')
        else:
            # Handle multipart messages
            parts = msg.get('payload').get('parts', [])
            data = next((part['body'].get('data', '') for part in parts 
                        if part['mimeType'] == 'text/plain' 
                        or part['mimeType'] == 'text/html'), '')

        if data:
            text = base64.urlsafe_b64decode(data).decode()
            # If HTML, extract text
            if '<html' in text.lower():
                soup = BeautifulSoup(text, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)
            return text
        return ""

    def format_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format email data into standardized structure"""
        try:
            msg = self.service.users().messages().get(
                userId='me', 
                id=email_data['id'], 
                format='full'
            ).execute()

            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')

            content = self.get_email_content(msg)

            safe_print(f"{Fore.GREEN}✓ Successfully processed email: {subject}{Style.RESET_ALL}")

            return {
                "id": email_data['id'],
                "slug": email_data['threadId'],
                "title": subject,
                "content": content,
                "publishedAt": date,
                "authorName": from_email,
                "category": "Email",
                "sourceName": self.source_name,
                "sourceUrl": self.source_url,
                "imageUrl": "",
                "articleUrl": f"https://mail.google.com/mail/u/0/#inbox/{email_data['id']}",
                "tags": ["email"]
            }
        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error processing email: {str(e)}{Style.RESET_ALL}")
            return None

    def clean_content(self, text: str) -> str:
        """Clean email content"""
        try:
            # Remove URLs
            text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
            
            # Remove special characters and extra whitespace
            text = re.sub(r'[\r\n\t]+', ' ', text)  # Replace newlines and tabs with space
            text = re.sub(r'\[.*?\]', '', text)  # Remove text in square brackets
            text = re.sub(r'\s+', ' ', text)  # Replace multiple spaces with single space
            text = re.sub(r'[^\w\s.,!?-]', '', text)  # Keep only alphanumeric and basic punctuation
            
            # Remove common email footers and headers
            footers = [
                "Manage your account",
                "Not financial or tax advice",
                "Disclosure",
                "Unsubscribe",
                "Terms & Conditions",
                "Privacy Policy",
                "See our Investment Disclosures"
            ]
            for footer in footers:
                text = text.split(footer)[0]
            
            # Clean up final text
            text = text.strip()
            return text
        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error cleaning content: {str(e)}{Style.RESET_ALL}")
            return text

    async def get_articles_async(
        self, page: int = 1, page_size: int = 20, pages_to_fetch: int = 3
    ) -> List[Dict[str, Any]]:
        """Get emails with pagination for multiple pages"""
        try:
            safe_print(f"{Fore.YELLOW}⟳ Fetching emails from Gmail...{Style.RESET_ALL}")
            
            all_formatted_emails = []
            next_page_token = None
            
            # Fetch specified number of pages
            for current_page in range(page, page + pages_to_fetch):
                # Get emails for current page
                results = self.service.users().messages().list(
                    userId='me',
                    maxResults=page_size,
                    pageToken=next_page_token
                ).execute()

                messages = results.get('messages', [])
                next_page_token = results.get('nextPageToken')

                # Process emails for current page
                formatted_emails = []
                for message in messages:
                    email_data = self.format_email(message)
                    if email_data:
                        # Clean the content
                        email_data["content"] = self.clean_content(email_data["content"])
                        email_data["clean_content"] = email_data["content"]
                        formatted_emails.append(email_data)

                all_formatted_emails.extend(formatted_emails)
                safe_print(f"{Fore.GREEN}✓ Successfully fetched page {current_page} ({len(formatted_emails)} emails){Style.RESET_ALL}")
                
                if not next_page_token:
                    break

            safe_print(f"{Fore.GREEN}✓ Total emails fetched: {len(all_formatted_emails)}{Style.RESET_ALL}")
            return all_formatted_emails

        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching emails: {str(e)}{Style.RESET_ALL}")
            return []

    def get_articles(self, page: int = 1, page_size: int = 20, pages_to_fetch: int = 3) -> List[Dict[str, Any]]:
        """Synchronous wrapper for get_articles_async"""
        async def run():
            return await self.get_articles_async(page, page_size, pages_to_fetch)
        return asyncio.run(run())

async def main_async():
    """Async main function for testing"""
    try:
        scraper = EmailScraper(max_concurrent=10)
        safe_print(f"{Fore.CYAN}Starting Email scraper...{Style.RESET_ALL}")
        articles = await scraper.get_articles_async(page=1)
        safe_print(f"{Fore.GREEN}✓ Scraping completed successfully{Style.RESET_ALL}")
        print(json.dumps(articles, indent=2))
    except Exception as e:
        safe_print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")

def main():
    """Main entry point"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main() 