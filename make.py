#!/usr/bin/env python3
# vim: sw=2 ts=2 sts=2 et

from __future__ import annotations

from collections.abc import Iterable
import re
import sys
import subprocess
import textwrap
import logging
import shlex
from shlex import quote
from dataclasses import dataclass, replace
from pprint import pprint
from collections import defaultdict

log = logging.getLogger(__name__)

@dataclass
class DashOption:
  shorts: list[str]
  longs: list[str]
  arg: str | None
  choices: list[tuple[str, str]]
  desc: str

@dataclass
class Subcommand:
  cmd: str
  desc: str
  dashes: list[DashOption]
  subs: list[Subcommand]
  args: list[tuple[str, str]]

def do_dash_option(s: str):
  s = s.lstrip()
  if not s or s[0] != '-': return
  lines = s.split('\n')

  options = []
  head = lines[0].split(' ')
  for x in head:
    options.append(x.rstrip(',.'))
    if not x.endswith(','):
      break
  args = head[len(options):]
  arg = args[0] if args else None
  assert len(args) <= 1

  rest = textwrap.dedent('\n'.join(lines[1:]))
  desc = rest.split('\n\n')[0].strip()

  shorts = [x for x in options if x.startswith('-') and not x.startswith('--')]
  longs = [x for x in options if x.startswith('--')]

  options = []
  if '\nPossible values:\n' in rest:
    options_split = ('\n' + rest.split('\nPossible values:\n', 1)[-1].strip()).split('\n- ')
    # XXX: assumes fixed argument choices have no spaces
    for t in options_split:
      if not t: continue
      opt, opt_desc = t.replace('- ', '', 1).split(maxsplit=1)
      if opt.endswith(':'): opt = opt[:-1]
      options.append((opt, opt_desc))

  return DashOption(shorts, longs, arg, options, desc)


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

reported = set()
def get_suggestion(data: DashOption, arg_suggestions: dict):
  arg = data.arg
  if arg is None:
    return ''
  if arg not in arg_suggestions and arg not in reported:
    log.warning(f'unknown arg string placeholder {arg}')
    reported.add(arg)

  if arg in arg_suggestions:
    suggestion = arg_suggestions[arg]
    if not isinstance(suggestion, str):
      suggestion = suggestion(data)
  elif arg:
    suggestion = '-a ' + quote(quote(arg))
  else:
    suggestion = ''
  return suggestion

def suggest(suggestion: str, desc: str | None = None):
  s = f'{quote(suggestion)}'
  if desc:
    s += quote('\t'+desc)
  return quote(f'{s}\n')

def suggest_list(l: Iterable[tuple[str,str]]):
  return '-a ' + ''.join(suggest(x, y) for x, y in l)

def make_fish_completion(data: Subcommand, prefix: str, arg_suggestions: dict | None = None):
  arg_suggestions = arg_suggestions or {}
  join = shlex.join
  cmd = prefix + data.cmd
  for dash in data.dashes:
    shorts = ''.join(join(['-s', a.lstrip('-')]) for a in dash.shorts)
    longs = ''.join(join(['-l', a.lstrip('-')]) for a in dash.longs)
    desc = quote(dash.desc)
    if dash.choices:
      args = '-r ' + suggest_list(dash.choices)
    else:
      args = get_suggestion(dash, arg_suggestions)

    print(f'complete -c {cmd} -f {shorts} {longs} -d {desc} {args}')

  if data.subs:
    allsubs = quote(join([x.cmd for x in data.subs]))
    print(f'complete -c {cmd} -f --condition "not __fish_seen_subcommand_from "{allsubs} {suggest_list((x.cmd, x.desc) for x in data.subs)}')
    for sub in data.subs:
      print(f'''complete -c {cmd} -f --condition "__fish_seen_subcommand_from {sub.cmd}" -a '(_myfish_complete_subcommand --fcs-set-argv0="{cmd}__{sub.cmd}")' ''')

  for sub in data.subs:
    print('')
    make_fish_completion(sub, cmd + '__', arg_suggestions)

  # print(f'complete -c {cmd} -f -a {quote('(_myfish_complete_subcommand --fcs-set-argv0="git checkout")')}')

def branchless_arg_map():
  def base_arg_for_difftool_or_move(x: DashOption):
    if 'difftool' in x.desc:
      return '-xa "(__fish_complete_path)"'
    elif 'commit inside a subtree' in x.desc:
      return "-r -ka '(__fish_git_commits)'"
    assert False, f'unexpected dashoption {x}'

  return {
    '<WORKING_DIRECTORY>': '-ra "(__fish_complete_directories)"',
    '<BASE>': base_arg_for_difftool_or_move,
    '<OUTPUT>': '-xa "(__fish_complete_path)"',
    '<MAIN_BRANCH_NAME>': "-r -ka '(__fish_git_branches)'",
    '<BRANCH_NAME>': "-r -ka '(__fish_git_branches)'",
    '<SOURCE>': "-xa '(__fish_git_commits)'",
    '<EXACT>': "-xa '(__fish_git_commits)'",
    '<DEST>': "-xa '(__fish_git_commits)'",
    '<MESSAGES>': '-r',
    '<CREATE>': '-r',
    '<COMMIT_TO_FIXUP>': "-xa '(__fish_git_commits)'",
    '<EVENT_ID>': '-r',  # XXX: smartlog "event id"???
    '<MESSAGE>': '-r',
    '<NUM_JOBS>': '-r',

    '<EXEC>': '-r',
    '<COMMAND>': '-r',
    '<JOBS>': '-r',
    '<GIT_EXECUTABLE>': '-xa "(__fish_complete_path)"',
  }

if __name__ == '__main__':
  root = explore(['git-branchless'])
  # pprint(cmds, width=140)
  make_fish_completion(root, '', branchless_arg_map())

  # for a number of git-branchless, these are aliased to the top-level git. duplicate the thingies
  aliased = ['amend', 'hide', 'move', 'next', 'prev', 'query', 'record', 'restack', 'reword', 'sl', 'smartlog', 'submit', 'sw', 'sync', 'test', 'undo', 'unhide']
  gitroot = replace(root, cmd='git', subs=[x for x in root.subs if x.cmd in aliased])
  make_fish_completion(gitroot, '', branchless_arg_map())

