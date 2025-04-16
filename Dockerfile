FROM python:3.8.7-slim-buster

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git jq wget apt-utils binutils gconf-service libasound2 libatk1.0-0 libcairo2 libcups2 libfontconfig1 libgdk-pixbuf2.0-0 libgtk-3-0 libnspr4 libpango-1.0-0 libxss1 fonts-liberation libappindicator1 libnss3 lsb-release xdg-utils libgbm1 libxkbfile1 ffmpeg xvfb curl chromium

RUN python3 -m pip install selenium boto3 pyvirtualdisplay gspread==3.0.0 oauth2client==4.1.2 google-api-python-client==1.7.9
RUN apt-get install -y iputils-ping
WORKDIR /app

COPY ./app/browser /app/browser
RUN dpkg -i /app/browser/Yandex.deb

COPY ./app/checker /app/checker

CMD [ "python3", "/app/checker/run.py" ]