"""
cron "13 18 * * *" script-path=xxx.py,tag=匹配cron用
new Env('夸克签到')

环境变量格式（QUARK_COOKIE）:
  单账号: user=张三; kps=xxxxxx; sign=xxxxxx; vcode=xxxxxx;
  多账号: 用 \n 或 && 分隔

kps/sign/vcode 从手机抓包获取，有效期约两个月。
抓包目标接口: https://drive-m.quark.cn/1/clouddrive/capacity/growth/info
"""
import os
import re
import sys
import time
import random
import requests
from datetime import datetime, timedelta

# ---------------- 通知模块 ----------------
hadsend = False
send = None
try:
    from notify import send
    hadsend = True
    print("✅ 已加载notify.py通知模块")
except ImportError:
    print("⚠️  未加载通知模块，跳过通知功能")

# 随机延迟配置
max_random_delay = int(os.getenv("MAX_RANDOM_DELAY", "10"))
random_signin = os.getenv("RANDOM_SIGNIN", "true").lower() == "true"

def Push(contents):
    if hadsend:
        try:
            send('夸克签到', contents)
            print('✅ notify.py推送成功')
        except Exception as e:
            print(f'❌ notify.py推送失败: {e}')
    else:
        print(f'📢 夸克签到\n{contents}')

def format_time_remaining(seconds):
    if seconds <= 0:
        return "立即执行"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}小时{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"

def wait_with_countdown(delay_seconds):
    if delay_seconds <= 0:
        return
    print(f"夸克签到需要等待 {format_time_remaining(delay_seconds)}")
    remaining = delay_seconds
    while remaining > 0:
        if remaining <= 10 or remaining % 10 == 0:
            print(f"倒计时: {format_time_remaining(remaining)}")
        sleep_time = 1 if remaining <= 10 else min(10, remaining)
        time.sleep(sleep_time)
        remaining -= sleep_time

def get_env():
    """
    读取 QUARK_COOKIE 环境变量，解析为 user_data dict 列表。
    格式: user=xxx; kps=xxx; sign=xxx; vcode=xxx;
    多账号用 \\n 或 && 分隔。
    """
    if "QUARK_COOKIE" not in os.environ:
        print('❌ 未添加QUARK_COOKIE变量')
        sys.exit(0)

    raw = os.environ.get('QUARK_COOKIE')
    cookie_list = re.split(r'\n|&&', raw)

    accounts = []
    for cookie_str in cookie_list:
        cookie_str = cookie_str.strip()
        if not cookie_str:
            continue
        user_data = {}
        for part in cookie_str.replace(" ", "").split(';'):
            part = part.strip()
            if part and '=' in part:
                k, v = part.split('=', 1)
                user_data[k] = v
        if user_data:
            accounts.append(user_data)

    if not accounts:
        print('❌ QUARK_COOKIE 解析失败，请检查格式')
        sys.exit(0)

    return accounts


class Quark:
    def __init__(self, user_data: dict):
        self.param = user_data

    def convert_bytes(self, b):
        units = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = 0
        while b >= 1024 and i < len(units) - 1:
            b /= 1024
            i += 1
        return f"{b:.2f} {units[i]}"

    def _base_params(self):
        """构造认证参数（kps/sign/vcode 作为 query params）"""
        return {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.param.get('kps'),
            "sign": self.param.get('sign'),
            "vcode": self.param.get('vcode'),
        }

    def get_growth_info(self):
        url = "https://drive-m.quark.cn/1/clouddrive/capacity/growth/info"
        try:
            response = requests.get(url=url, params=self._base_params(), timeout=15)
            print(f"  [growth/info] HTTP {response.status_code} → {response.text[:300]}")
            data = response.json()
            return data.get("data", False)
        except Exception as e:
            print(f"  [growth/info] 异常: {e}")
            return False

    def get_growth_sign(self):
        url = "https://drive-m.quark.cn/1/clouddrive/capacity/growth/sign"
        try:
            response = requests.post(
                url=url,
                json={"sign_cyclic": True},
                params=self._base_params(),
                timeout=15
            )
            print(f"  [growth/sign] HTTP {response.status_code} → {response.text[:300]}")
            data = response.json()
            if data.get("data"):
                return True, data["data"]["sign_daily_reward"]
            return False, data.get("message", "未知错误")
        except Exception as e:
            print(f"  [growth/sign] 异常: {e}")
            return False, str(e)

    def do_sign(self):
        log = ""
        username = self.param.get('user', '未知用户')

        growth_info = self.get_growth_info()
        if not growth_info:
            log += f"  用户: {username}\n"
            log += "  ❌ 获取签到信息失败（kps/sign/vcode 可能已过期，请重新抓包）\n"
            return log

        is_vip = '88VIP' if growth_info.get('88VIP') else '普通用户'
        total_cap = self.convert_bytes(growth_info.get('total_capacity', 0))
        sign_reward_cap = self.convert_bytes(
            growth_info.get('cap_composition', {}).get('sign_reward', 0)
        )
        log += f"  {'🌟' if growth_info.get('88VIP') else '👤'} {is_vip} {username}\n"
        log += f"  💾 网盘总容量: {total_cap}，签到累计容量: {sign_reward_cap}\n"

        cap_sign = growth_info.get("cap_sign", {})
        if cap_sign.get("sign_daily"):
            # 今日已签到
            log += (
                f"  ✅ 今日已签到: +{self.convert_bytes(cap_sign['sign_daily_reward'])}，"
                f"连签进度({cap_sign['sign_progress']}/{cap_sign['sign_target']})\n"
            )
        else:
            # 执行签到
            ok, sign_return = self.get_growth_sign()
            if ok:
                log += (
                    f"  ✅ 签到成功: 今日+{self.convert_bytes(sign_return)}，"
                    f"连签进度({cap_sign['sign_progress'] + 1}/{cap_sign['sign_target']})\n"
                )
            else:
                log += f"  ❌ 签到失败: {sign_return}\n"

        return log


def main():
    msg = ""
    accounts = get_env()
    print(f"✅ 检测到共 {len(accounts)} 个夸克账号\n")

    for i, user_data in enumerate(accounts):
        header = f"🙍🏻‍♂️ 第{i+1}个账号\n"
        print(header, end="")
        msg += header

        result = Quark(user_data).do_sign()
        print(result)
        msg += result + "\n"

        if i < len(accounts) - 1:
            delay = random.uniform(3, 8)
            print(f"随机等待 {delay:.1f} 秒后处理下一个账号...")
            time.sleep(delay)

    Push(contents=msg.rstrip("\n"))
    return msg.rstrip("\n")


if __name__ == "__main__":
    print(f"==== 夸克网盘签到开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")
    if random_signin:
        delay_seconds = random.randint(0, max_random_delay)
        if delay_seconds > 0:
            signin_time = datetime.now() + timedelta(seconds=delay_seconds)
            print(f"随机模式: 延迟 {format_time_remaining(delay_seconds)} 后签到")
            print(f"预计签到时间: {signin_time.strftime('%H:%M:%S')}")
            wait_with_countdown(delay_seconds)
    print("----------夸克网盘开始尝试签到----------")
    main()
    print("----------夸克网盘签到执行完毕----------")
    print(f"==== 夸克签到完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")
