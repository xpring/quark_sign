# quark_sign
夸克网盘自动签到青龙脚本

感谢“https://github.com/waj1994/quark-auto-check-in/tree/master”

25年12月前：

kps/sign/vcode 放在 HTTP header 的 cookie 字段里
用完整 URL 当环境变量


25年12月后：

kps/sign/vcode 作为 URL query 参数（?kps=xxx&sign=xxx&vcode=xxx）
不需要任何 header cookie
