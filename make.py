#!/usr/bin/env python3
# vim: sw=2 ts=2 sts=2 et

from __future__ import annotations

import re
import sys
import subprocess
import textwrap
import shlex
from shlex import quote
from dataclasses import dataclass
from pprint import pprint
from collections import defaultdict

@dataclass
class DashOptions:
  shorts: list[str]
  longs: list[str]
  args: list[str]
  desc: str

@dataclass
class Subcommand:
  cmd: str
  desc: str
  dashes: list[DashOptions]
  subs: list[Subcommand]
  args: list[tuple[str, str]]

def do_dash_option(s: str):
  s = s.lstrip()
  if not s or s[0] != '-': return
  lines = s.split('\n')

  options = []
  head = lines[0].split(' ')
  for x in head:
    options.append(x.rstrip(','))
    if not x.endswith(','):
      break
  args = head[len(options):]

  desc = textwrap.dedent('\n'.join(lines[1:])).split('\n\n')[0].strip()

  shorts = [x for x in options if x.startswith('-') and not x.startswith('--')]
  longs = [x for x in options if x.startswith('--')]

  return DashOptions(shorts, longs, args, desc)


def do_arg(s: str):
  s = s.lstrip()
  if not s: return
  lines = s.split('\n')

  head = lines[0].strip()

  desc = textwrap.dedent('\n'.join(lines[1:])).split('\n\n')[0].strip()

  return (head, desc)

def explore(cmd: list[str]):

  help = subprocess.check_output(cmd + ['--help'], encoding='utf-8')

  # sections: dict[str, list[dict]] = {}
  # section = ''
  # split = [''] + help.split('\n')
  # for prev, l in zip(split, split[1:]):
  #   l = l.rstrip()
  #   if not l: continue
  #   indent = len(l) - len(l.lstrip())
  #   indent //= 2
  #   print(indent, l)

  # https://stackoverflow.com/questions/61464503/python-re-library-string-split-but-keep-the-delimiters-separators-as-part-of-the
  dash_options = (re.split(r'^(?=\s+-\S)', help, flags=re.MULTILINE))

  dashes = [y for x in dash_options if (y := do_dash_option(x))]

  try:
    command_text = help.split('\nOptions:\n')[0].split('\nCommands:\n')[1]
  except IndexError:
    command_text = ''
  subs = []
  for l in command_text.split('\n'):
    l = l.strip()
    if not l: continue
    name, desc = l.split(maxsplit=1)
    if name == 'help':
      subcmd = Subcommand('help', 'Print this message or the help of the given subcommand(s)', [], [], [])
    else:
      subcmd = explore(cmd + [name])
      subcmd.desc = desc
    subs.append(subcmd)


  try:
    args_text = help.split('\nOptions:\n')[0].split('\nArguments:\n')[1]
  except IndexError:
    args_text = ''

  args_split = re.split(r'^(?=  \S)', args_text, flags=re.MULTILINE)
  args = [y for x in args_split if (y := do_arg(x))]

  return Subcommand(cmd[-1], '', dashes, subs, args)

def make_arg(arg: str):
  print(arg, file=sys.stderr)
  if arg.startswith('['):
    return f'-a {quote(quote(arg))}'
  elif arg.startswith('<'):
    return f'-ra {quote(quote(arg))}'
  assert False, 'unhandled arg prefix ' + repr(arg)

def suggest(suggestion: str, desc: str | None = None):
  s = f'{quote(suggestion)}'
  if desc:
    s += quote('\t'+desc)
  return quote(f'{s}\n')

def make_fish_completion(data: Subcommand, prefix: str):
  join = shlex.join
  cmd = prefix + data.cmd
  for dash in data.dashes:
    shorts = ''.join(join(['-s', a.lstrip('-')]) for a in dash.shorts)
    longs = ''.join(join(['-l', a.lstrip('-')]) for a in dash.longs)
    desc = quote(dash.desc)
    assert len(dash.args) <= 1
    args = make_arg(dash.args[0]) if dash.args else ''

    print(f'complete -c {cmd} -f {shorts} {longs} -d {desc} {args}')

  if data.subs:
    allsubs = quote(join([x.cmd for x in data.subs]))
    print(f'complete -c {cmd} -f --condition "not __fish_seen_subcommand_from "{allsubs} -a {''.join(suggest(x.cmd, x.desc) for x in data.subs)}')
    for sub in data.subs:
      print(f'''complete -c {cmd} -f --condition "__fish_seen_subcommand_from {sub.cmd}" -a '(_myfish_complete_subcommand --fcs-set-argv0="{cmd}__{sub.cmd}")' ''')

  for sub in data.subs:
    print('')
    make_fish_completion(sub, cmd + '__')

  # print(f'complete -c {cmd} -f -a {quote('(_myfish_complete_subcommand --fcs-set-argv0="git checkout")')}')

if __name__ == '__main__':
  cmds = explore(['git-branchless'])
  # pprint(cmds, width=140)
  make_fish_completion(cmds, '')
