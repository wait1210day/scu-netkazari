# SCU Netkazari
Netkazari / ネットかざり - Research on the campus network of Sichuan University

四川大学校园网研究与一些实用工具

## Tools

一些实用工具保存在 [//tools](./tools) 目录下.

* [//tools/automata.py](./tools/automata.py): 校园网自动认证登录 Python 脚本
* [//tools/dnstunnel.py](./tools/dnstunnel.py): 利用 DNS 隧道免认证上网，原理见
[//papers/etherswitch.md](./papers/etherswitch.md).
**该工具仅仅是用于学习概念和进行网络实验的原型，请勿长期用于逃避校园网认证上网，否则后果自负.**

所有工具都是由 Python 写成的，因此直接安装相关依赖即可，建议使用虚拟环境：

```bash
$ python -m venv venv
$ source venv/bin/activate
$ pip install --upgrade pip
# For automata.py:
$ pip install requests scapy regex
# For dnstunnel.py:
$ pip install python-pytun
```

**DNS Tunnel**: 要使用 `dnstunnel.py` 工具，安装好依赖后需要填写该脚本的配置，
这些配置记录在脚本头部，按注释说明的进行修改即可：

```python
#!/usr/bin/env python3

import socket
...
SERVER_IP = 'xxx.xxx.xxx.xxx'       # For server, IP
CLIENT_IFACE = 'wlan0'              # For client, sending package from which iface, use `None` for default

...
```

然后在服务端，确保 53 端口没有被占用（它极有可能被 `systemd-resolved` 占用，如果是这样的话，
暂时停止这个服务即可），然后运行脚本：
```bash
$ sudo ./dnstunnel.py server
```

在客户端，运行：
```bash
$ sudo ./dnstunnel.py client
```

此时，服务端和客户端都会被创建一个名为 `kztun0` 的网卡设备，服务端被设置 IP `10.1.1.1`，
客户端被设置 IP `10.1.1.2`，然后二者就可以使用这个网卡进行基于 IPv4 协议的通讯了，
可以在客户端使用 `10.1.1.1` 访问服务端，反之亦然，**而无论客户端是否有校园网认证**.
例如：可以跑 ssh 开一个 socks5 代理来上网:

```bash
$ ssh -ND 1080 your_user_name@10.1.1.1
```

## Research

[//papers](./papers) 下是一些关于校园网认证机制的研究.

* [//papers/etherswitch.md](./papers/etherswitch.md) 描述了校园网网络层的交换策略，以及它如何与验证机制配合. 同时提及了 DNS 隧道.