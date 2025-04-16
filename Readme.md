### Docker image to run Yandex browser to check domain ban. Purpose  
The goal is to identify erroneous website blocks by the browser.

#### Command to run
```
docker build -t browser_based_domain_checker .  
  
docker run \
    -e AWS_ACCESS_KEY_ID=XXXXXX \
    -e AWS_SECRET_ACCESS_KEY=XXXXXXXXXXXX \
    -e AWS_DEFAULT_REGION=us-central-1 \
    -e SPREADSHEET_ID=XXXXXXXXXXXXXXXXXX \
    -e WORKSHEET_NAME=XXXXXX \
    -e GOOGLE_API_KEY_BUCKET_S3=google-s3-bucket \
    -e GOOGLE_API_KEY_KEY_S3=yandex-domain-check/ga-service-account.json \
    -e RESULT_S3_BUCKET=result-s3-bucket \
    -e RESULT_S3_KEY=yandex.json \
    browser_based_domain_checker
```

### Workflow
1. A Google API key is downloaded from AWS S3 using the specified bucket (`GOOGLE_API_KEY_BUCKET_S3`) and key (`GOOGLE_API_KEY_KEY_S3`).
2. The specified worksheet (`WORKSHEET_NAME`) from the Google Spreadsheet (`SPREADSHEET_ID`) is parsed, and the `domain` and `source` columns are extracted.
3. The list of domains is divided into 10 equal parts.
4. Ten instances of the Yandex Browser (or another browser of your choice) are launched using the Selenium framework. Each browser instance processes its own subset of domains.
5. If a website is blocked by the browser, the `safe-browsing-blocking-page` tag is detected on the page, and the domain is marked as blocked.
6. The results of the checks are uploaded to AWS S3 in the specified bucket (`RESULT_S3_BUCKET`) and key (`RESULT_S3_KEY`).  

##### Chrome seem to crash in Docker containers on certain pages due to too small /dev/shm. So you may have to fix the small /dev/shm size.
```
sudo mount -t tmpfs -o rw,nosuid,nodev,noexec,relatime,size=512M tmpfs /dev/shm
```  
It also works if you use -v /dev/shm:/dev/shm option to share host /dev/shm. Chrome_options `--disable-dev-shm-usage` will force Chrome to use the /tmp directory, this may slow down the execution though since disk will be used instead of memory.
