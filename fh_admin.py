#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Farm Helper - админ-утилита аккаунтов (только стандартная библиотека Python 3.8+).

Файлы рядом со скриптом:
  accounts.json - ПУБЛИЧНЫЙ файл (его скачивает Farm Helper с GitHub): аккаунты, баны, сроки.
  codes.json    - ПРИВАТНЫЙ файл: уникальные коды (в .gitignore, на GitHub не попадает!).

Примеры:
  python fh_admin.py code-new --tier premium --time 30d --count 5     # создать 5 premium-кодов на 30 дней
  python fh_admin.py code-new --tier user --time 7d                    # обычный код на 7 дней
  python fh_admin.py import "FHREG1|ivan|...|...|FH-XXXX-XXXX-XXXX|..."  # одобрить заявку игрока
  python fh_admin.py ban ivan --time 3d --reason "флуд"               # бан на 3 дня (без --time = навсегда)
  python fh_admin.py unban ivan
  python fh_admin.py sub ivan --add 1d12h                              # продлить подписку
  python fh_admin.py sub ivan --set 90m                                # срок = 90 минут от сейчас
  python fh_admin.py sub ivan --forever                                # бессрочно
  python fh_admin.py tier ivan premium                                 # сменить тип аккаунта
  python fh_admin.py users                                             # список аккаунтов
  python fh_admin.py push                                              # git add/commit/push accounts.json

Время: число + единица, можно склеивать: 45s, 90m, 12h, 30d, 2w, 1d12h30m. 0 или forever = бессрочно.
"""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ACC = os.path.join(BASE, 'accounts.json')
CODES = os.path.join(BASE, 'codes.json')
UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # без похожих символов (0/O, 1/I)


def die(msg):
    print('ОШИБКА: ' + msg)
    sys.exit(1)


def sha(s):
    import hashlib
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    os.replace(tmp, path)


def load_acc():
    d = load(ACC, {})
    d.setdefault('version', 1)
    d.setdefault('settings', {'disabled': False, 'message': ''})
    d.setdefault('users', {})
    return d


def load_codes():
    return load(CODES, {})


def parse_duration(text):
    t = str(text).strip().lower()
    if t in ('0', 'forever', 'inf', 'perm', 'навсегда'):
        return 0
    if t.isdigit():
        die('укажите единицу времени, например %sd или %sh (s/m/h/d/w)' % (t, t))
    if not re.fullmatch(r'(\d+[smhdw])+', t):
        die('не понимаю время "%s". Примеры: 45s, 90m, 12h, 30d, 1d12h' % text)
    return sum(int(n) * UNITS[u] for n, u in re.findall(r'(\d+)([smhdw])', t))


def fmt_left(sec):
    sec = int(sec)
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return ('%dд ' % d if d else '') + '%02d:%02d:%02d' % (h, m, s)


def fmt_ts(ts):
    return time.strftime('%d.%m.%Y %H:%M', time.localtime(ts))


def status(u, now=None):
    now = now or time.time()
    if u.get('banned'):
        return 'БАН навсегда'
    if u.get('ban_until', 0) > now:
        return 'БАН до %s (%s)' % (fmt_ts(u['ban_until']), fmt_left(u['ban_until'] - now))
    ex = u.get('expires', 0)
    if ex and ex <= now:
        return 'подписка истекла %s' % fmt_ts(ex)
    return 'активен, ' + ('бессрочно' if not ex else 'осталось ' + fmt_left(ex - now))


def get_user(acc, login):
    login = login.lower()
    if login not in acc['users']:
        die('аккаунт "%s" не найден' % login)
    return login, acc['users'][login]


# ---------------------------------------------------------------- команды
def cmd_code_new(a):
    secs = parse_duration(a.time)
    codes = load_codes()
    made = []
    for _ in range(a.count):
        while True:
            code = 'FH-' + '-'.join(''.join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))
            if code not in codes:
                break
        codes[code] = {'tier': a.tier, 'seconds': secs, 'used_by': '', 'revoked': False,
                       'note': a.note or '', 'created': int(time.time())}
        made.append(code)
    save(CODES, codes)
    left = 'бессрочно' if not secs else fmt_left(secs)
    print('Созданы коды (%s, подписка %s):' % (a.tier, left))
    for c in made:
        print('  ' + c)
    print('Коды лежат в codes.json (приватный файл, не публикуйте).')


def cmd_codes(a):
    codes = load_codes()
    if not codes:
        print('Кодов нет.')
    for c, v in sorted(codes.items()):
        st = 'ОТОЗВАН' if v.get('revoked') else ('занят: ' + v['used_by'] if v.get('used_by') else 'свободен')
        left = 'бессрочно' if not v['seconds'] else fmt_left(v['seconds'])
        print('%-20s %-8s %-12s %s %s' % (c, v['tier'], left, st, ('# ' + v['note']) if v.get('note') else ''))


def cmd_code_revoke(a):
    codes = load_codes()
    c = a.code.upper()
    if c not in codes:
        die('код не найден')
    codes[c]['revoked'] = True
    save(CODES, codes)
    print('Код %s отозван (если им уже пользовались - заблокируйте аккаунт командой ban).' % c)


def cmd_import(a):
    req = a.request.strip().strip('"\'')
    parts = req.split('|')
    if len(parts) != 6 or parts[0] != 'FHREG1':
        die('это не заявка Farm Helper (ожидается FHREG1|логин|соль|хеш|код|hwid)')
    _, login, salt, h, code, hwid = parts
    if not re.fullmatch(r'[a-z0-9_]{3,20}', login):
        die('неверный логин в заявке')
    if not re.fullmatch(r'[0-9a-f]{8,32}', salt) or not re.fullmatch(r'[0-9a-f]{64}', h):
        die('неверные соль/хеш в заявке')
    if not re.fullmatch(r'[A-Z0-9-]{4,40}', code):
        die('неверный код в заявке')
    acc, codes = load_acc(), load_codes()
    if login in acc['users']:
        die('логин "%s" уже занят' % login)
    c = codes.get(code)
    if not c:
        die('код %s не найден в codes.json - заявку НЕ одобряем' % code)
    if c.get('revoked'):
        die('код %s отозван' % code)
    if c.get('used_by'):
        die('код %s уже использован аккаунтом %s' % (code, c['used_by']))
    now = int(time.time())
    secs = c['seconds']
    acc['users'][login] = {
        'salt': salt, 'hash': h, 'code_hash': sha('code:' + code), 'tier': c['tier'],
        'expires': (now + secs) if secs else 0, 'banned': False, 'ban_until': 0, 'ban_reason': '',
        'hwid': hwid.upper(), 'created': now,
    }
    c['used_by'] = login
    save(ACC, acc)
    save(CODES, codes)
    print('Аккаунт %s создан: %s, %s.' % (login, c['tier'], status(acc['users'][login])))
    print('Теперь выполните: python fh_admin.py push')


def cmd_users(a):
    acc = load_acc()
    if not acc['users']:
        print('Аккаунтов нет.')
    for login, u in sorted(acc['users'].items()):
        print('%-20s %-8s %s' % (login, u.get('tier', 'user'), status(u)))


def cmd_info(a):
    acc = load_acc()
    login, u = get_user(acc, a.login)
    print('Логин:    ' + login)
    print('Тип:      ' + u.get('tier', 'user'))
    print('Статус:   ' + status(u))
    if u.get('ban_reason'):
        print('Причина:  ' + u['ban_reason'])
    print('HWID:     ' + (u.get('hwid') or 'не привязан'))
    print('Создан:   ' + fmt_ts(u.get('created', 0)))


def cmd_ban(a):
    acc = load_acc()
    login, u = get_user(acc, a.login)
    if a.time:
        secs = parse_duration(a.time)
    else:
        secs = 0
    if secs:
        u['banned'], u['ban_until'] = False, int(time.time()) + secs
    else:
        u['banned'], u['ban_until'] = True, 0
    u['ban_reason'] = a.reason or ''
    save(ACC, acc)
    print('%s: %s' % (login, status(u)))
    print('Выполните push. Бан вступит в силу у игрока при ближайшей проверке (до ~10 минут + кэш GitHub).')


def cmd_unban(a):
    acc = load_acc()
    login, u = get_user(acc, a.login)
    u['banned'], u['ban_until'], u['ban_reason'] = False, 0, ''
    save(ACC, acc)
    print('%s: %s' % (login, status(u)))


def cmd_sub(a):
    acc = load_acc()
    login, u = get_user(acc, a.login)
    now = int(time.time())
    if a.forever:
        u['expires'] = 0
    elif a.expire_now:
        u['expires'] = now
    elif a.set is not None:
        secs = parse_duration(a.set)
        u['expires'] = (now + secs) if secs else 0
    else:
        secs = parse_duration(a.add)
        base = max(u.get('expires', 0), now) if u.get('expires', 0) else now
        if u.get('expires', 0) == 0 and secs:
            base = now  # у бессрочного аккаунта "добавить" = ограничить сроком от сейчас
        u['expires'] = base + secs if secs else 0
    save(ACC, acc)
    print('%s: %s' % (login, status(u)))


def cmd_tier(a):
    acc = load_acc()
    login, u = get_user(acc, a.login)
    u['tier'] = a.tier
    save(ACC, acc)
    print('%s: тип = %s' % (login, a.tier))


def cmd_hwid_reset(a):
    acc = load_acc()
    login, u = get_user(acc, a.login)
    u['hwid'] = (a.set or '').upper()
    save(ACC, acc)
    print('%s: HWID = %s' % (login, u['hwid'] or 'пусто (вход с любого ПК)'))


def cmd_delete(a):
    acc = load_acc()
    login, _ = get_user(acc, a.login)
    del acc['users'][login]
    save(ACC, acc)
    print('Аккаунт %s удалён.' % login)


def cmd_maintenance(a):
    acc = load_acc()
    acc['settings'] = {'disabled': a.state == 'on', 'message': a.message or ''}
    save(ACC, acc)
    print('Технический режим: ' + a.state)


def cmd_push(a):
    def run(*args):
        r = subprocess.run(args, cwd=BASE, capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        if out:
            print(out)
        return r.returncode
    run('git', 'add', 'accounts.json')
    run('git', 'commit', '-m', a.message)
    if run('git', 'push') != 0:
        die('git push не удался (проверьте вход в GitHub)')
    print('Готово: accounts.json опубликован.')


def main():
    p = argparse.ArgumentParser(description='Farm Helper: управление аккаунтами')
    sp = p.add_subparsers(dest='cmd', required=True)

    c = sp.add_parser('code-new', help='создать уникальные коды')
    c.add_argument('--tier', choices=['user', 'premium'], default='user')
    c.add_argument('--time', default='30d', help='срок подписки: 45s, 90m, 12h, 30d, 1d12h, forever')
    c.add_argument('--count', type=int, default=1)
    c.add_argument('--note', default='')
    c.set_defaults(f=cmd_code_new)

    sp.add_parser('codes', help='список кодов').set_defaults(f=cmd_codes)

    c = sp.add_parser('code-revoke', help='отозвать неиспользованный код')
    c.add_argument('code')
    c.set_defaults(f=cmd_code_revoke)

    c = sp.add_parser('import', help='одобрить заявку игрока')
    c.add_argument('request')
    c.set_defaults(f=cmd_import)

    sp.add_parser('users', help='список аккаунтов').set_defaults(f=cmd_users)

    c = sp.add_parser('info', help='подробности об аккаунте')
    c.add_argument('login')
    c.set_defaults(f=cmd_info)

    c = sp.add_parser('ban', help='забанить (без --time - навсегда)')
    c.add_argument('login')
    c.add_argument('--time', default='')
    c.add_argument('--reason', default='')
    c.set_defaults(f=cmd_ban)

    c = sp.add_parser('unban', help='снять бан')
    c.add_argument('login')
    c.set_defaults(f=cmd_unban)

    c = sp.add_parser('sub', help='срок подписки')
    c.add_argument('login')
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument('--add', help='продлить на (1d12h)')
    g.add_argument('--set', help='срок от текущего момента')
    g.add_argument('--forever', action='store_true')
    g.add_argument('--expire-now', action='store_true', dest='expire_now')
    c.set_defaults(f=cmd_sub)

    c = sp.add_parser('tier', help='сменить тип: user / premium')
    c.add_argument('login')
    c.add_argument('tier', choices=['user', 'premium'])
    c.set_defaults(f=cmd_tier)

    c = sp.add_parser('hwid-reset', help='сбросить привязку к ПК (или задать новый HWID через --set)')
    c.add_argument('login')
    c.add_argument('--set', default='', help='новый HWID из заявки игрока')
    c.set_defaults(f=cmd_hwid_reset)

    c = sp.add_parser('delete', help='удалить аккаунт')
    c.add_argument('login')
    c.set_defaults(f=cmd_delete)

    c = sp.add_parser('maintenance', help='отключить/включить скрипт для всех')
    c.add_argument('state', choices=['on', 'off'])
    c.add_argument('--message', default='')
    c.set_defaults(f=cmd_maintenance)

    c = sp.add_parser('push', help='опубликовать accounts.json на GitHub')
    c.add_argument('-m', '--message', default='update accounts')
    c.set_defaults(f=cmd_push)

    a = p.parse_args()
    a.f(a)


if __name__ == '__main__':
    main()
