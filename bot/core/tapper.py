import json
import asyncio
from time import time
from random import randint
from urllib.parse import unquote

import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestWebView

from bot.config import settings
from bot.utils import logger
from bot.utils.scripts import escape_html, is_jwt_valid
from bot.exceptions import InvalidSession
from .headers import headers


class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            if not self.tg_client.is_connected:
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            dialogs = self.tg_client.get_dialogs()
            async for dialog in dialogs:
                if dialog.chat and dialog.chat.username and dialog.chat.username == 'wcoin_tapbot':
                    break

            while True:
                try:
                    peer = await self.tg_client.resolve_peer('wcoin_tapbot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    fls *= 2
                    logger.info(f"{self.session_name} | Sleep {fls}s")

                    await asyncio.sleep(fls)

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=peer,
                bot=peer,
                platform='android',
                from_bot_menu=False,
                url='https://starfish-app-fknmx.ondigitalocean.app/alohomora/'
            ))

            auth_url = web_view.url
            tg_web_data = unquote(
                string=unquote(
                    string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0]))

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(
                f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def login(self, http_client: aiohttp.ClientSession, tg_web_data: str, base_url: str, user_id: str) -> str:
        response_text = ''
        try:
            response = await http_client.post(url=base_url, json={"identifier": user_id, "password": user_id})
            response_text = await response.text()
            response.raise_for_status()
            response_json = await response.json()
            return response_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while getting Access Token: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(delay=3)

    async def get_me_telegram(self, http_client: aiohttp.ClientSession, url: str) -> dict[str]:
        response_text = ''

        try:
            response = await http_client.get(url=url)
            response_text = await response.text()
            response.raise_for_status()

            response_json = await response.json()
            # tasks = response_json['telegramUser']

            return response_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while getting Me Telegram: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(delay=3)

    async def send_taps(self, http_client: aiohttp.ClientSession, url: str,  data: dict[str]) -> dict[str]:
        response_text = ''
        try:
            response = await http_client.put(url=url, json=data)
            response_text = await response.text()
            if response.status != 422:
                response.raise_for_status()

            response_json = json.loads(response_text)
            # player_data = response_json.get('clickerUser') or response_json.get(
            #     'found', {}).get('clickerUser', {})

            return response_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while Tapping: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(delay=3)

        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(
                f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(
                f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def run(self, proxy: str | None) -> None:
        access_token = ''
        user_data = {}
        hit_min = False
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
        http_client = aiohttp.ClientSession(
            headers=headers, connector=proxy_conn)

        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)

        tg_web_data = await self.get_tg_web_data(proxy=proxy)
        user_id = tg_web_data.split('"id":')[1].split(',')[0].strip()
        query_id = tg_web_data.split('query_id=', maxsplit=1)[
            1].split('&user', maxsplit=1)[0]
        user_details = tg_web_data.split('user=', maxsplit=1)[
            1].split('&auth_date', maxsplit=1)[0]
        auth_date = tg_web_data.split('auth_date=', maxsplit=1)[
            1].split('&hash', maxsplit=1)[0]
        hash_ = tg_web_data.split('hash=', maxsplit=1)[1]

        base_url = f'https://starfish-app-fknmx.ondigitalocean.app/wapi/api/auth/local?hash=query_id={query_id}&user={user_details}&auth_date={auth_date}&hash={hash_}'
        get_me_details_url = f'https://starfish-app-fknmx.ondigitalocean.app/wapi/api/users/me?timestamp={int(time())}}}&hash=query_id={query_id}&user={user_details}&auth_date={auth_date}&hash={hash_}'

        while True:
            try:
                if http_client.closed:
                    if proxy_conn:
                        if not proxy_conn.closed:
                            proxy_conn.close()

                    proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
                    http_client = aiohttp.ClientSession(
                        headers=headers, connector=proxy_conn)

                if not is_jwt_valid(access_token):
                    login_data = await self.login(http_client=http_client, tg_web_data=tg_web_data, base_url=base_url, user_id=user_id)
                    access_token = login_data['jwt']

                    if not access_token:
                        logger.error(
                            f"{self.session_name} | Failed fetch token | Sleep {60:,}s")
                        await asyncio.sleep(delay=60)
                        continue
                    http_client.headers["Authorization"] = f"Bearer {access_token}"
                    user_data = await self.get_me_telegram(http_client=http_client, url=get_me_details_url)
                    logger.error(
                        f"{user_data} | Failed fetch token | Sleep {60:,}s")
                    

     

                http_client.headers["Authorization"] = f"Bearer {access_token}"
                if not user_data:
                    user_data = await self.get_me_telegram(http_client=http_client, url=get_me_details_url)
                if hit_min:
                    user_data["energy"] = 1000
                    hit_min = False
                if int(user_data["energy"]) < settings.MIN_AVAILABLE_ENERGY:
                    random_sleep = randint(
                        settings.SLEEP_BY_MIN_ENERGY[0], settings.SLEEP_BY_MIN_ENERGY[1])
                    logger.info(
                        f"{self.session_name} | energy is zero | Sleep {random_sleep:,}s")
                    hit_min = True
                    await asyncio.sleep(delay=random_sleep)
                    continue

                random_taps = randint(a=20, b=80)

                if (int(user_data["energy"]) < random_taps):
                    random_taps = user_data["energy"]

                tap_data = {
                    "id": user_data["id"],
                    "clicks": int(user_data["clicks"]) + random_taps,
                    "energy":  int(user_data["energy"]) - random_taps,
                    "balance":  int(user_data['balance']) + random_taps,
                    "balance_from_clicks": int(user_data["balance_from_clicks"]) + random_taps,
                    "last_click_at": int(time()),
                }
                send_taps_url = f'https://starfish-app-fknmx.ondigitalocean.app/wapi/api/users/{user_data["id"]}?timestamp={int(time())}&hash=query_id={query_id}&user={user_details}&auth_date={auth_date}&hash={hash_}'

                response = await self.send_taps(http_client=http_client, url=send_taps_url, data=tap_data)

                logger.success(f"{self.session_name} | Successful tapped! | "
                               f"Balance: <c>{int(user_data['balance']):,}</c> (<g>+{int(random_taps):,}</g>) | Total: <e>{int(response['balance']):,}</e>")
                user_data = response

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=3)

            else:
                sleep_between_clicks = randint(
                    a=settings.SLEEP_BETWEEN_TAP[0], b=settings.SLEEP_BETWEEN_TAP[1])

                logger.info(f"Sleep {sleep_between_clicks}s")
                await asyncio.sleep(delay=sleep_between_clicks)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
