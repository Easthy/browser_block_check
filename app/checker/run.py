import os
import sys
from tempfile import NamedTemporaryFile
import boto3
from botocore.exceptions import ClientError
import json
import time
import logging
from datetime import datetime
from pyvirtualdisplay import Display
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from googleapiclient.discovery import build
from selenium import webdriver
import multiprocessing


logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger()

display = Display(visible=0, size=[800, 600])
display.start()

options = webdriver.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--allow-running-insecure-content")
options.add_argument('--disable-gpu')
options.add_argument('--disable-dev-shm-usage')    

binary_yandex_driver_file = '/app/browser/yandexdriver'

# Start several instances of Browser as selenium is not thread safe
browsers = []
num_threads = 10
for i in range(0, num_threads):
    browsers.append({'driver': webdriver.Chrome(binary_yandex_driver_file, options=options)})

class GoogleSpreadSheerParser():
    """
    Class for parsing Google Spreadsheet domain list to check via browser
    """
    SCOPES_READONLY = 'https://www.googleapis.com/auth/spreadsheets.readonly'
    
    def __init__(self,
                 spreadsheet_id,
                 worksheet_name,
                 google_api_key_bucket_s3,
                 google_api_key_key_s3,
                 api_type='sheets',
                 api_version='v4'):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self.google_api_key_bucket_s3 = google_api_key_bucket_s3
        self.google_api_key_key_s3 = google_api_key_key_s3
        self.api_type = api_type
        self.api_version = api_version

    def parse(self):
        conn = self._get_conn()
        spreadsheet = conn.open_by_key(self.spreadsheet_id)
        records = spreadsheet.worksheet(self.worksheet_name).get_all_records()
        return records

    def _get_credentials(self, scopes):
        google_api_key = self._get_google_api_key(self.google_api_key_bucket_s3, self.google_api_key_key_s3)
        return ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict=json.loads(google_api_key), scopes=scopes)

    def _get_conn(self, scopes=SCOPES_READONLY, **kwargs):
        credentials = self._get_credentials(scopes)
        return gspread.authorize(credentials)

    def _get_google_api_key(self, google_api_key_bucket_s3, google_api_key_key_s3):
        """
        Read Google API key from AWS S3
        """
        s3 = boto3.resource('s3')
        obj = s3.Object(google_api_key_bucket_s3, google_api_key_key_s3)
        return obj.get()['Body'].read().decode('utf-8') 


def get_domains():
    """
    Call Google spreadsheet parser
    """
    spreadsheet_id = os.environ.get('SPREADSHEET_ID')
    worksheet_name = os.environ.get('WORKSHEET_NAME')
    google_api_key_bucket_s3 = os.environ.get('GOOGLE_API_KEY_BUCKET_S3')
    google_api_key_key_s3 = os.environ.get('GOOGLE_API_KEY_KEY_S3')

    parser =  GoogleSpreadSheerParser(
        spreadsheet_id=spreadsheet_id,
        worksheet_name=worksheet_name,
        google_api_key_bucket_s3=google_api_key_bucket_s3,
        google_api_key_key_s3=google_api_key_key_s3
    )
    rows = parser.parse()
    domains = []
    for row in rows:
        row = {k.lower(): str(v) for k, v in row.items()}
        # Check if domain is active (has no 'd' (discarded))
        if row.get('renew_month').isdecimal():
            domains.append({
                'domain': row.get('domain'),
                'source': row.get('source')
            })

    return domains


def check_domain(driver, urls_to_check, num_thread=None, checked_domains=[]):
    """
    Checking the range of domains with certain browser instance
    """
    for url in urls_to_check:
        logger.info(f"Checking for {url.get('domain')}; {url.get('source')}; thread {num_thread}")
        try:
            driver.get('https://' + url.get('domain'))
            title = driver.title
            safe_browser_tag = driver.find_elements_by_tag_name("safe-browsing-blocking-page")
            safe_browser_page_text = safe_browser_tag[0].text if len(safe_browser_tag) > 0 else None
            if safe_browser_page_text:
                logger.info(f"Possibly {url.get('domain')} banned by Yandex, title {title}; thread {num_thread}")

            checked_domains.append({
                'domain': url.get('domain'),
                'date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
                'browser': 'yandex-browser',
                'page_title': title,
                'safe_browser_page_text': safe_browser_page_text,
                'banned': True if safe_browser_page_text else False,
                'source': url.get('source', None)
            })

        except Exception as e:   
            logger.info(f"Exception during domain check:\n {e}")


def upload_to_s3(checked_domains):
    """
    Format and load check result to AWS S3
    """
    logger.info('Uploading to S3 started')
    result_s3_bucket = os.environ.get('RESULT_S3_BUCKET')
    result_s3_key = os.environ.get('RESULT_S3_KEY')

    tmp_file_handle = NamedTemporaryFile(delete=True)

    checked_domains = "\n".join([json.dumps(row) for row in checked_domains])
    tmp_file_handle = NamedTemporaryFile(delete=True)
    tmp_file_handle.write(checked_domains.encode('utf-8'))
    tmp_file_handle.seek(0)

    s3 = boto3.client('s3')
    try:
        response = s3.upload_file(tmp_file_handle.name, result_s3_bucket, result_s3_key)
    except ClientError as e:
        logging.error(e)
        return False
    return True

def chunks(seq, num):
    """
    Split domains for checking into several equal lists
    """
    avg = len(seq) / float(num)
    out = []
    last = 0.0
    while last < len(seq):
        out.append(seq[int(last):int(last + avg)])
        last += avg
    return out

################################
urls_to_check = get_domains()
urls_to_check_chunks = chunks(urls_to_check, num_threads)

jobs = []
manager = multiprocessing.Manager()
checked_domains = manager.list()

for num_thread, browser in enumerate(browsers):
    logger.info(f'Thread {num_thread} will check {len(urls_to_check_chunks[num_thread])} domains')
    p = multiprocessing.Process(
        target = check_domain,
        kwargs={
            'driver': browser['driver'], 
            'urls_to_check': urls_to_check_chunks[num_thread],
            'num_thread': num_thread,
            'checked_domains': checked_domains
        }
    )
    jobs.append(p)
    p.start()

for process in jobs:
    process.join()

logger.info('Checking finished')
upload_result = upload_to_s3(checked_domains)
logger.info(f'Uploading to S3 finished {"successfully" if upload_result else "with errors"}')
