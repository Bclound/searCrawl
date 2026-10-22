#!/bin/sh
set -eu
# 首次启动生成随机密钥，之后保留配置卷中的设置。
if [ ! -f /etc/searxng/settings.yml ]; then
    cp /opt/searcrawl-settings.yml /etc/searxng/settings.yml
    secret=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9')
    sed -i "s/__SEARCRAWL_SECRET__/$secret/" /etc/searxng/settings.yml
fi
exec /usr/local/searxng/entrypoint.sh
