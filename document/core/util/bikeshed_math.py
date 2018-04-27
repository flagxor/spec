#! /usr/bin/env python
# -*- coding: latin-1 -*-

import Queue
import os
import re
import shelve
import subprocess
import sys
import threading


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


def FindMatching(data, prefix):
  start = data.find(prefix)
  if start < 0:
    return (None, None)
  end = start + 1
  total = 0
  while True:
    if data[end] == '{':
      total += 1
    elif data[end] == '}':
      total -= 1
      if total == 0:
        end += 1
        break
    end += 1
  return (start, end)


def ReplaceMath(cache, data):
  old = data
  data = data.replace('\\\\', '\\DOUBLESLASH')
  data = data.replace('\\(', '')
  data = data.replace('\\)', '')
  data = data.replace('\\[', '')
  data = data.replace('\\]', '')
  data = data.replace('\\DOUBLESLASH', '\\\\')
  data = data.replace('’', '\\text{’}')
  data = data.replace('‘', '\\text{‘}')
  data = data.replace('\\hfill', '')
  data = data.replace('\\mbox', '\\mathrel')
  data = data.replace('\\begin{split}', '\\begin{aligned}')
  data = data.replace('\\end{split}', '\\end{aligned}')
  data = data.replace('&amp;', '&')
  data = data.replace('&lt;', '<')
  data = data.replace('&gt;', '>')
  data = data.replace('{array}[t]', '{array}')
  data = data.replace('{array}[b]', '{array}')
  data = data.replace('@{~}', '')
  data = data.replace('@{}', '')
  data = data.replace('@{\\qquad}', '')
  data = data.replace('@{\\qquad\\qquad}', '')
  data = re.sub('([^\\\\])[$]', '\\1', data)
  data = '\\mathrm{' + data + '}'

  if cache.has_key(data):
    return cache[data]

  macros = {}
  while True:
    start, end = FindMatching(data, '\\def\\')
    if start is None:
      break
    parts = data[start:end]
    name_end = parts.find('#')
    assert name_end > 0
    name = parts[len('\\def'):name_end]
    value = parts[name_end+len('#1'):end]
    macros[name] = value
    data = data[:start] + data[end:]
  for k, v in macros.iteritems():
    while True:
      start, end = FindMatching(data, k + '{')
      if start is None:
        break
      data = data[:start] + v.replace('#1', data[start+len(k):end]) + data[end:]
  p = subprocess.Popen(
      ['node', os.path.join(SCRIPT_DIR, 'katex/cli.js'), '--display-mode'],
      stdin=subprocess.PIPE, stdout=subprocess.PIPE)
  ret = p.communicate(input=data)[0]
  if p.returncode != 0:
    sys.stderr.write('BEFORE:\n' + old + '\n')
    sys.stderr.write('AFTER:\n' + data + '\n')
    return ''
  ret = ret.strip()
  ret = ret[ret.find('<span class="katex-html"'):]
  ret = '<span class="katex-display"><span class="katex">' + ret + '</span>'
  # w3c validator does not like negative em.
  ret = re.sub('height:[-][0-9][.][0-9]+em', 'height:0em', ret)
  # Fix ahref -> a href bug (fixed in next release).
  # Also work around W3C forcing links to have underline.
  ret = ret.replace('<ahref="<a', '<a style="border-bottom: 0px" href="')
  # Fix stray spans that come out of katex.
  ret = re.sub('[<]span class="vlist" style="height:[0-9.]+em;"[>]',
               '<span class="vlist">', ret)
  # Drop bad italic font adjustment.
  # https://github.com/WebAssembly/spec/issues/669
  # https://github.com/Khan/KaTeX/issues/1259
  ret = re.sub(
      'mathit" style="margin-right:0.[0-9]+em', 'mathit" style="', ret)
  ret = re.sub(
      'mainit" style="margin-right:0.[0-9]+em', 'mathit" style="', ret)

  cache[data] = ret
  return ret


def Main():
  data = sys.stdin.read()
  cache = shelve.open('math.cache')
  sys.stdout.write(data)
  cache.close()


Main()
