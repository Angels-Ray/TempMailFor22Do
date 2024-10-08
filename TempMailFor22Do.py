import logging
from functools import wraps
import secrets
import string
from typing import List, Optional, Dict, Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


def api_error_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.HTTPError as http_err:
            raise Exception(f"HTTP error occurred: {http_err}")
        except requests.exceptions.RequestException as req_err:
            raise Exception(f"Request error occurred: {req_err}")
        except Exception as e:
            raise Exception(f"An error occurred: {e}")

    return wrapper


class BaseApiClient:
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'

    def __init__(self, mail='', ssl_verify=False, proxy_url=None):
        self.ssl_verify = ssl_verify
        self.post_headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            'User-Agent': self.UA,
            'X-Requested-With': 'XMLHttpRequest',
        }
        self.get_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": self.UA,
            'X-Requested-With': 'XMLHttpRequest',

        }
        self.proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }
        self.cookies = {
            'PHPSESSID': self.generate_name(26),
            'mail': ''
        }

    def generate_name(self, size: int = 8) -> str:
        """ 生成一个指定长度的随机UTF-8字符串 """
        characters = string.ascii_letters + string.digits
        return ''.join(secrets.choice(characters) for _ in range(size))

    def _make_request(self, method: str, url: str, headers: Optional[Dict] = None,
                      data: Optional[Dict] = None, to_json: bool = True) -> Any:
        headers = headers or {}

        if method == 'GET':
            response = requests.get(
                url, cookies=self.cookies, headers=headers, proxies=self.proxies, verify=self.ssl_verify, timeout=5)
        elif method == 'POST':
            response = requests.post(
                url, cookies=self.cookies, headers=headers, data=data, proxies=self.proxies, verify=self.ssl_verify, timeout=5)
        elif method == 'DELETE':
            response = requests.delete(
                url, cookies=self.cookies, headers=headers, data=data, proxies=self.proxies, verify=self.ssl_verify, timeout=5)
        else:
            raise ValueError("Unsupported HTTP method.")

        if response.status_code == 401:
            raise Exception(
                "Unauthorized request. Please check your credentials.")

        response.raise_for_status()
        if to_json:
            return response.json()
        else:
            response.encoding = 'utf-8'
            return response.text


class TempEmailManager(BaseApiClient):
    BASE_URL = 'https://22.do'

    def __init__(self, mail: str = '', ssl_verify: bool = False, proxy_url: Optional[str] = None, log_level: int = logging.INFO):
        super().__init__(mail, ssl_verify, proxy_url)

        self.logger = logging.getLogger(f"{__name__}.TempEmailManager")
        self.logger.setLevel(log_level)

    @api_error_handler
    def generate_gmail(self, set_to_self: bool = True) -> Optional[str]:
        url = f'{self.BASE_URL}/zh/mailbox/generate'
        data = {'type': 'Gmail'}
        data = self._make_request(
            'POST', url, headers=self.post_headers, data=data)
        if data.get('action', '') == 'OK':
            email = data['data']['address']['email']
            if set_to_self:
                self.cookies['mail'] = email
            return email

    @api_error_handler
    def generate_high_quality_gmail(self, dots: int = 2, retry: int = 30) -> Optional[str]:
        for i in range(retry):
            email = self.generate_gmail(set_to_self=True)
            if email and len(email.split('.')) <= (dots+2) and "gmail" in email:
                return email
            logger.debug(f"重试第 {i+1} 次...")
        return None

    @api_error_handler
    def change_email(self, set_to_self: bool = False) -> Optional[str]:
        url = f'{self.BASE_URL}/zh/mailbox/change'
        data = self._make_request('POST', url, headers=self.post_headers)
        if data.get('action', '') == 'OK':
            email = data['data']['address']['email']
            if set_to_self:
                self.cookies['mail'] = email
            return email

    @api_error_handler
    def check_new(self) -> List[Dict[str, str]]:
        """ "Msg":[{"mailId":"xxx","from":"XXX <xxx@xxx.cn>","subject":"subjectXXXXX:","time":"17秒前"}] """
        if not self.cookies['mail']:
            logger.error("未选择邮箱。")
            raise ValueError("未选择邮箱。")
        url = f'{self.BASE_URL}/zh/mailbox/check'
        data = self._make_request('GET', url, headers=self.get_headers)
        return data.get('Msg', []) if data.get('action') == 'OK' else []

    def get_email_content(self, mail_id: str) -> str:
        url = f'{self.BASE_URL}/zh/content/{mail_id}/html'
        return self._make_request('GET', url, headers=self.get_headers, to_json=False)


def main():
    import time

    # app = TempEmailManager(proxy_url='127.0.0.1:8888')
    app = TempEmailManager()

    print("生成新邮箱...")
    email = app.generate_high_quality_gmail(dots=2)
    if email:
        print(f"邮箱: {email}")
    else:
        print("生成邮箱失败。")
        return

    print("等待新邮件...")
    while True:
        print("Checking new mails...")
        new_mails = app.check_new()
        if new_mails:
            for mail in new_mails:
                print(f"收到来自 {mail['from']} 的新邮件: {mail['subject']}")
                content = app.get_email_content(mail['mailId'])
                print(content)
            break
        time.sleep(3)


if __name__ == '__main__':
    main()
