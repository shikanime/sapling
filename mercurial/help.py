# help.py - help data for mercurial
#
# Copyright 2006 Matt Mackall <mpm@selenic.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from __future__ import absolute_import

import itertools
import os
import textwrap

from . import (
    cmdutil,
    encoding,
    error,
    extensions,
    filemerge,
    fileset,
    minirst,
    pycompat,
    revset,
    templatefilters,
    templatekw,
    templater,
    util,
)
from .hgweb import webcommands
from .i18n import _, gettext


_exclkeywords = {
    "(ADVANCED)",
    "(DEPRECATED)",
    "(EXPERIMENTAL)",
    # i18n: "(ADVANCED)" is a keyword, must be translated consistently
    _("(ADVANCED)"),
    # i18n: "(DEPRECATED)" is a keyword, must be translated consistently
    _("(DEPRECATED)"),
    # i18n: "(EXPERIMENTAL)" is a keyword, must be translated consistently
    _("(EXPERIMENTAL)"),
}


def listexts(header, exts, indent=1, showdeprecated=False):
    """return a text listing of the given extensions"""
    rst = []
    if exts:
        for name, desc in sorted(exts.iteritems()):
            if not showdeprecated and any(w in desc for w in _exclkeywords):
                continue
            rst.append("%s:%s: %s\n" % (" " * indent, name, desc))
    if rst:
        rst.insert(0, "\n%s\n\n" % header)
    return rst


def extshelp(ui):
    rst = loaddoc("extensions")(ui).splitlines(True)
    rst.extend(
        listexts(_("Enabled extensions:"), extensions.enabled(), showdeprecated=True)
    )
    rst.extend(listexts(_("Disabled extensions:"), extensions.disabled()))
    doc = "".join(rst)
    return doc


def optrst(header, options, verbose):
    data = []
    multioccur = False
    for option in options:
        if len(option) == 5:
            shortopt, longopt, default, desc, optlabel = option
        else:
            shortopt, longopt, default, desc = option
            optlabel = _("VALUE")  # default label

        if not verbose and any(w in desc for w in _exclkeywords):
            continue

        so = ""
        if shortopt:
            so = "-" + shortopt
        lo = "--" + longopt
        if default:
            # default is of unknown type, and in Python 2 we abused
            # the %s-shows-repr property to handle integers etc. To
            # match that behavior on Python 3, we do str(default) and
            # then convert it to bytes.
            desc += _(" (default: %s)") % pycompat.bytestr(default)

        if isinstance(default, list):
            lo += " %s [+]" % optlabel
            multioccur = True
        elif (default is not None) and not isinstance(default, bool):
            lo += " %s" % optlabel

        data.append((so, lo, desc))

    if not data:
        return ""

    if multioccur:
        header += _(" ([+] can be repeated)")

    rst = ["\n%s:\n\n" % header]
    rst.extend(minirst.maketable(data, 1))

    return "".join(rst)


def indicateomitted(rst, omitted, notomitted=None):
    rst.append("\n\n.. container:: omitted\n\n    %s\n\n" % omitted)
    if notomitted:
        rst.append("\n\n.. container:: notomitted\n\n    %s\n\n" % notomitted)


def filtercmd(ui, cmd, kw, doc):
    if not ui.debugflag and cmd.startswith("debug") and kw != "debug":
        return True
    if not ui.verbose and doc and any(w in doc for w in _exclkeywords):
        return True
    return False


def topicmatch(ui, commands, kw):
    """Return help topics matching kw.

    Returns {'section': [(name, summary), ...], ...} where section is
    one of topics, commands, extensions, or extensioncommands.
    """
    kw = encoding.lower(kw)

    def lowercontains(container):
        return kw in encoding.lower(container)  # translated in helptable

    results = {"topics": [], "commands": [], "extensions": [], "extensioncommands": []}
    for names, header, doc in helptable:
        # Old extensions may use a str as doc.
        if (
            sum(map(lowercontains, names))
            or lowercontains(header)
            or (callable(doc) and lowercontains(doc(ui)))
        ):
            results["topics"].append((names[0], header))
    for cmd, entry in commands.table.iteritems():
        if len(entry) == 3:
            summary = entry[2]
        else:
            summary = ""
        # translate docs *before* searching there
        docs = _(pycompat.getdoc(entry[0])) or ""
        if kw in cmd or lowercontains(summary) or lowercontains(docs):
            doclines = docs.splitlines()
            if doclines:
                summary = doclines[0]
            cmdname = cmd.partition("|")[0].lstrip("^")
            if filtercmd(ui, cmdname, kw, docs):
                continue
            results["commands"].append((cmdname, summary))
    for name, docs in itertools.chain(
        extensions.enabled(False).iteritems(), extensions.disabled().iteritems()
    ):
        if not docs:
            continue
        name = name.rpartition(".")[-1]
        if lowercontains(name) or lowercontains(docs):
            # extension docs are already translated
            results["extensions"].append((name, docs.splitlines()[0]))
        try:
            mod = extensions.load(ui, name, "")
        except ImportError:
            # debug message would be printed in extensions.load()
            continue
        for cmd, entry in getattr(mod, "cmdtable", {}).iteritems():
            if kw in cmd or (len(entry) > 2 and lowercontains(entry[2])):
                cmdname = cmd.partition("|")[0].lstrip("^")
                cmddoc = pycompat.getdoc(entry[0])
                if cmddoc:
                    cmddoc = gettext(cmddoc).splitlines()[0]
                else:
                    cmddoc = _("(no help text available)")
                if filtercmd(ui, cmdname, kw, cmddoc):
                    continue
                results["extensioncommands"].append((cmdname, cmddoc))
    return results


def loaddoc(topic, subdir=None):
    """Return a delayed loader for help/topic.txt."""

    def loader(ui):
        docdir = os.path.join(util.datapath, "help")
        if subdir:
            docdir = os.path.join(docdir, subdir)
        path = os.path.join(docdir, topic + ".txt")
        doc = gettext(util.readfile(path))
        for rewriter in helphooks.get(topic, []):
            doc = rewriter(ui, topic, doc)
        return doc

    return loader


internalstable = sorted(
    [
        (["bundles"], _("Bundles"), loaddoc("bundles", subdir="internals")),
        (["censor"], _("Censor"), loaddoc("censor", subdir="internals")),
        (
            ["changegroups"],
            _("Changegroups"),
            loaddoc("changegroups", subdir="internals"),
        ),
        (["config"], _("Config Registrar"), loaddoc("config", subdir="internals")),
        (
            ["requirements"],
            _("Repository Requirements"),
            loaddoc("requirements", subdir="internals"),
        ),
        (["revlogs"], _("Revision Logs"), loaddoc("revlogs", subdir="internals")),
        (
            ["wireprotocol"],
            _("Wire Protocol"),
            loaddoc("wireprotocol", subdir="internals"),
        ),
    ]
)


def internalshelp(ui):
    """Generate the index for the "internals" topic."""
    lines = ['To access a subtopic, use "hg help internals.{subtopic-name}"\n', "\n"]
    for names, header, doc in internalstable:
        lines.append(" :%s: %s\n" % (names[0], header))

    return "".join(lines)


helptable = sorted(
    [
        (["bundlespec"], _("Bundle File Formats"), loaddoc("bundlespec")),
        (["color"], _("Colorizing Outputs"), loaddoc("color")),
        (["config", "hgrc"], _("Configuration Files"), loaddoc("config")),
        (["dates"], _("Date Formats"), loaddoc("dates")),
        (["flags"], _("Command-line flags"), loaddoc("flags")),
        (["patterns"], _("File Name Patterns"), loaddoc("patterns")),
        (["environment", "env"], _("Environment Variables"), loaddoc("environment")),
        (
            ["revisions", "revs", "revsets", "revset", "multirevs", "mrevs"],
            _("Specifying Revisions"),
            loaddoc("revisions"),
        ),
        (["filesets", "fileset"], _("Specifying File Sets"), loaddoc("filesets")),
        (["diffs"], _("Diff Formats"), loaddoc("diffs")),
        (
            ["merge-tools", "mergetools", "mergetool"],
            _("Merge Tools"),
            loaddoc("merge-tools"),
        ),
        (
            ["templating", "templates", "template", "style"],
            _("Template Usage"),
            loaddoc("templates"),
        ),
        (["urls"], _("URL Paths"), loaddoc("urls")),
        (["extensions"], _("Using Additional Features"), extshelp),
        (["subrepos", "subrepo"], _("Subrepositories"), loaddoc("subrepos")),
        (["hgweb"], _("Configuring hgweb"), loaddoc("hgweb")),
        (["glossary"], _("Glossary"), loaddoc("glossary")),
        (
            ["hgignore", "ignore"],
            _("Syntax for Mercurial Ignore Files"),
            loaddoc("hgignore"),
        ),
        (["phases"], _("Working with Phases"), loaddoc("phases")),
        (
            ["scripting"],
            _("Using Mercurial from scripts and automation"),
            loaddoc("scripting"),
        ),
        (["internals"], _("Technical implementation topics"), internalshelp),
        (["pager"], _("Pager Support"), loaddoc("pager")),
    ]
)

# Maps topics with sub-topics to a list of their sub-topics.
subtopics = {"internals": internalstable}

# Map topics to lists of callable taking the current topic help and
# returning the updated version
helphooks = {}


def addtopichook(topic, rewriter):
    helphooks.setdefault(topic, []).append(rewriter)


def makeitemsdoc(ui, topic, doc, marker, items, dedent=False):
    """Extract docstring from the items key to function mapping, build a
    single documentation block and use it to overwrite the marker in doc.
    """
    entries = []
    for name in sorted(items):
        text = (pycompat.getdoc(items[name]) or "").rstrip()
        if not text or not ui.verbose and any(w in text for w in _exclkeywords):
            continue
        text = gettext(text)
        if dedent:
            # Abuse latin1 to use textwrap.dedent() on bytes.
            text = textwrap.dedent(text.decode("latin1")).encode("latin1")
        lines = text.splitlines()
        doclines = [(lines[0])]
        for l in lines[1:]:
            # Stop once we find some Python doctest
            if l.strip().startswith(">>>"):
                break
            if dedent:
                doclines.append(l.rstrip())
            else:
                doclines.append("  " + l.strip())
        entries.append("\n".join(doclines))
    entries = "\n\n".join(entries)
    return doc.replace(marker, entries)


def makesubcmdlist(cmd, subcommands, verbose, quiet):
    cmdhelp = []
    for name, entry in subcommands.items():
        aliases = cmdutil.parsealiases(name)
        name = ", ".join(aliases) if verbose else aliases[0]
        doc = pycompat.getdoc(entry[0]) or ""
        doc, __, rest = doc.strip().partition("\n")
        if verbose and rest.strip():
            if len(entry) > 2:  # synopsis
                name = "{} {}".format(name, entry[2])
        cmdhelp.append(" :%s: %s\n" % (name, doc))
    rst = ["\n%s:\n\n" % _("subcommands")]
    rst.extend(sorted(cmdhelp))
    if not quiet:
        rst.append(
            _("\n(use 'hg help %s [subcommand]' to show complete subcommand help)\n")
            % cmd
        )
    return rst


def addtopicsymbols(topic, marker, symbols, dedent=False):
    def add(ui, topic, doc):
        return makeitemsdoc(ui, topic, doc, marker, symbols, dedent=dedent)

    addtopichook(topic, add)


addtopicsymbols(
    "bundlespec", ".. bundlecompressionmarker", util.bundlecompressiontopics()
)
addtopicsymbols("filesets", ".. predicatesmarker", fileset.symbols)
addtopicsymbols("merge-tools", ".. internaltoolsmarker", filemerge.internalsdoc)
addtopicsymbols("revisions", ".. predicatesmarker", revset.symbols)
addtopicsymbols("templates", ".. keywordsmarker", templatekw.keywords)
addtopicsymbols("templates", ".. filtersmarker", templatefilters.filters)
addtopicsymbols("templates", ".. functionsmarker", templater.funcs)
addtopicsymbols("hgweb", ".. webcommandsmarker", webcommands.commands, dedent=True)

helphomecommands = [
    ("Create repositories", {"init", "clone"}),
    ("Examine files in your current checkout", {"status", "grep"}),
    ("Work on your current checkout", {"add", "remove", "rename", "copy"}),
    ("Commit changes and modify commits", {"commit", "amend", "absorb", "metaedit"}),
    ("Look at commits and commit history", {"log", "show", "diff", "smartlog"}),
    ("Checkout other commits", {"checkout", "next", "previous"}),
    ("Rearrange commits", {"rebase", "histedit", "fold", "split", "graft", "hide"}),
    ("Undo changes", {"undo", "uncommit", "unamend", "redo"}),
    ("Exchange commits with a server", {"pull", "push", "prefetch"}),
]

helphometopics = {"revisions", "glossary", "patterns", "templating"}


class _helpdispatch(object):
    def __init__(
        self, ui, commands, unknowncmd=False, full=False, subtopic=None, **opts
    ):
        self.ui = ui
        self.commands = commands
        self.subtopic = subtopic
        self.unknowncmd = unknowncmd
        self.full = full
        self.opts = opts

    def dispatch(self, name):
        queries = []
        if self.unknowncmd:
            queries += [self.helpextcmd]
        if self.opts.get("extension"):
            queries += [self.helpext]
        if self.opts.get("command"):
            queries += [self.helpcmd]
        if not queries:
            queries = (self.helptopic, self.helpcmd, self.helpext, self.helpextcmd)
        for f in queries:
            try:
                return f(name, self.subtopic)
            except error.UnknownCommand:
                pass
        else:
            if self.unknowncmd:
                raise error.UnknownCommand(name)
            else:
                msg = _("no such help topic: %s") % name
                hint = _("try 'hg help --keyword %s'") % name
                raise error.Abort(msg, hint=hint)

    def helpcmd(self, name, subtopic=None):
        try:
            cmd, args, aliases, entry = cmdutil.findsubcmd(
                name.split(), self.commands.table, strict=self.unknowncmd, partial=True
            )
        except error.AmbiguousCommand as inst:
            # py3k fix: except vars can't be used outside the scope of the
            # except block, nor can be used inside a lambda. python issue4617
            prefix = inst.args[0]
            select = lambda c: c.lstrip("^").partition("|")[0].startswith(prefix)
            rst = self.helplist(name, select)
            return rst
        except error.UnknownSubcommand as inst:
            cmd, subcmd, __ = inst
            msg = _("'%s' has no such subcommand: %s") % (cmd, subcmd)
            hint = _("run 'hg help %s' to see available subcommands") % cmd
            raise error.Abort(msg, hint=hint)

        rst = []

        # check if it's an invalid alias and display its error if it is
        if getattr(entry[0], "badalias", None):
            rst.append(entry[0].badalias + "\n")
            if entry[0].unknowncmd:
                try:
                    rst.extend(self.helpextcmd(entry[0].cmdname))
                except error.UnknownCommand:
                    pass
            return rst

        # synopsis
        if len(entry) > 2:
            if entry[2].startswith("hg"):
                rst.append("%s\n" % entry[2])
            else:
                rst.append("hg %s %s\n" % (cmd, entry[2]))
        else:
            rst.append("hg %s\n" % cmd)
        # aliases
        if self.full and not self.ui.quiet and len(aliases) > 1:
            rst.append(_("\naliases: %s\n") % ", ".join(aliases[1:]))
        rst.append("\n")

        # description
        doc = gettext(pycompat.getdoc(entry[0]))
        if not doc:
            doc = _("(no help text available)")
        if util.safehasattr(entry[0], "definition"):  # aliased command
            source = entry[0].source
            if entry[0].definition.startswith("!"):  # shell alias
                doc = _("shell alias for::\n\n    %s\n\ndefined by: %s\n") % (
                    entry[0].definition[1:],
                    source,
                )
            else:
                doc = _("alias for: hg %s\n\n%s\n\ndefined by: %s\n") % (
                    entry[0].definition,
                    doc,
                    source,
                )
        doc = doc.splitlines(True)
        if self.ui.quiet or not self.full:
            rst.append(doc[0])
        else:
            rst.extend(doc)
        rst.append("\n")

        # check if this command shadows a non-trivial (multi-line)
        # extension help text
        try:
            mod = extensions.find(name)
            doc = gettext(pycompat.getdoc(mod)) or ""
            if "\n" in doc.strip():
                msg = _("(use 'hg help -e %s' to show help for the %s extension)") % (
                    name,
                    name,
                )
                rst.append("\n%s\n" % msg)
        except KeyError:
            pass

        # options
        if not self.ui.quiet and entry[1]:
            rst.append(optrst(_("Options"), entry[1], self.ui.verbose))

        if self.ui.verbose:
            rst.append(
                optrst(_("Global options"), self.commands.globalopts, self.ui.verbose)
            )

        # subcommands
        if entry[0].subcommands:
            rst.extend(
                makesubcmdlist(
                    cmd, entry[0].subcommands, self.ui.verbose, self.ui.quiet
                )
            )

        if not self.ui.verbose:
            if not self.full:
                rst.append(_("\n(use 'hg %s -h' to show more help)\n") % name)
            elif not self.ui.quiet:
                rst.append(
                    _("\n(some details hidden, use --verbose to show complete help)")
                )

        return rst

    def helpcmdlist(self, name, select=None):
        h = {}
        cmds = {}
        for c, e in self.commands.table.iteritems():
            if select and not select(c):
                continue
            f = c.lstrip("^").partition("|")[0]
            doc = pycompat.getdoc(e[0])
            if filtercmd(self.ui, f, name, doc):
                continue
            doc = gettext(doc)
            if doc:
                doc = doc.splitlines()[0].rstrip()
            if not doc:
                doc = _("(no help text available)")
            h[f] = doc
            cmds[f] = c.lstrip("^")

        if not h:
            return [], {}
        rst = []
        fns = sorted(h)
        for f in fns:
            if self.ui.verbose:
                commacmds = cmds[f].replace("|", ", ")
                rst.append(" :%s: %s\n" % (commacmds, h[f]))
            else:
                rst.append(" :%s: %s\n" % (f, h[f]))
        return rst, cmds

    def helplist(self, name, select=None, **opts):
        # list of commands
        rst, cmds = self.helpcmdlist(name, select)
        if not rst:
            if not self.ui.quiet:
                rst.append(_("no commands defined\n"))
            return rst

        if not self.ui.quiet:
            if name == "debug":
                header = _("Debug commands (internal and unsupported):\n\n")
            else:
                header = _("Commands:\n\n")
            rst.insert(0, header)

        return rst

    def helphome(self):
        rst = [
            _("Mercurial Distributed SCM\n"),
            "\n",
            "hg COMMAND [OPTIONS]\n",
            "\n",
            "These are some common Mercurial commands.  Use 'hg help commands' to list all "
            "commands, and 'hg help COMMAND' to get help on a specific command.\n",
            "\n",
        ]

        for desc, commands in helphomecommands:

            def match(cmdspec):
                return any(c in commands for c in cmdspec.lstrip("^").split("|"))

            sectionrst, sectioncmds = self.helpcmdlist(None, match)
            if sectionrst:
                rst.append(desc + ":\n\n")
                rst.extend(sectionrst)
                rst.append("\n")

        topics = []
        for names, header, doc in helptable:
            if names[0] in helphometopics:
                topics.append((names[0], header))
        if topics:
            rst.append(_("\nAdditional help topics:\n\n"))
            for t, desc in topics:
                rst.append(" :%s: %s\n" % (t, desc.lower()))

        return rst

    def helptopic(self, name, subtopic=None):
        # Look for sub-topic entry first.
        header, doc = None, None
        if subtopic and name in subtopics:
            for names, header, doc in subtopics[name]:
                if subtopic in names:
                    break

        if not header:
            for names, header, doc in helptable:
                if name in names:
                    break
            else:
                raise error.UnknownCommand(name)

        rst = [minirst.section(header)]

        # description
        if not doc:
            rst.append("    %s\n" % _("(no help text available)"))
        if callable(doc):
            rst += ["    %s\n" % l for l in doc(self.ui).splitlines()]

        if not self.ui.verbose:
            omitted = _("(some details hidden, use --verbose to show complete help)")
            indicateomitted(rst, omitted)

        try:
            cmdutil.findcmd(name, self.commands.table)
            rst.append(
                _("\nuse 'hg help -c %s' to see help for the %s command\n")
                % (name, name)
            )
        except error.UnknownCommand:
            pass
        return rst

    def helpext(self, name, subtopic=None):
        try:
            mod = extensions.find(name)
            doc = gettext(pycompat.getdoc(mod)) or _("no help text available")
        except KeyError:
            mod = None
            doc = extensions.disabledext(name)
            if not doc:
                raise error.UnknownCommand(name)

        if "\n" not in doc:
            head, tail = doc, ""
        else:
            head, tail = doc.split("\n", 1)
        rst = [_("%s extension - %s\n\n") % (name.rpartition(".")[-1], head)]
        if tail:
            rst.extend(tail.splitlines(True))
            rst.append("\n")

        if not self.ui.verbose:
            omitted = _("(some details hidden, use --verbose to show complete help)")
            indicateomitted(rst, omitted)

        if mod:
            try:
                ct = mod.cmdtable
            except AttributeError:
                ct = {}
            rst.extend(self.helplist(name, ct.__contains__))
        else:
            rst.append(
                _(
                    "(use 'hg help extensions' for information on enabling"
                    " extensions)\n"
                )
            )
        return rst

    def helpextcmd(self, name, subtopic=None):
        cmd, ext, mod = extensions.disabledcmd(
            self.ui, name, self.ui.configbool("ui", "strict")
        )
        doc = gettext(pycompat.getdoc(mod))
        if doc is None:
            doc = _("(no help text available)")
        else:
            doc = doc.splitlines()[0]

        rst = listexts(
            _("'%s' is provided by the following extension:") % cmd,
            {ext: doc},
            indent=4,
            showdeprecated=True,
        )
        rst.append("\n")
        rst.append(
            _("(use 'hg help extensions' for information on enabling extensions)\n")
        )
        return rst


def help_(ui, commands, name, unknowncmd=False, full=True, subtopic=None, **opts):
    """
    Generate the help for 'name' as unformatted restructured text. If
    'name' is None, describe the commands available.
    """

    opts = pycompat.byteskwargs(opts)
    dispatch = _helpdispatch(ui, commands, unknowncmd, full, subtopic, **opts)

    rst = []
    kw = opts.get("keyword")
    if kw or name is None and any(opts[o] for o in opts):
        matches = topicmatch(ui, commands, name or "")
        helpareas = []
        if opts.get("extension"):
            helpareas += [("extensions", _("Extensions"))]
        if opts.get("command"):
            helpareas += [("commands", _("Commands"))]
        if not helpareas:
            helpareas = [
                ("topics", _("Topics")),
                ("commands", _("Commands")),
                ("extensions", _("Extensions")),
                ("extensioncommands", _("Extension Commands")),
            ]
        for t, title in helpareas:
            if matches[t]:
                rst.append("%s:\n\n" % title)
                rst.extend(minirst.maketable(sorted(matches[t]), 1))
                rst.append("\n")
        if not rst:
            msg = _("no matches")
            hint = _("try 'hg help' for a list of topics")
            raise error.Abort(msg, hint=hint)
    elif name == "commands":
        if not ui.quiet:
            rst = [_("Mercurial Distributed SCM\n"), "\n"]
        rst.extend(dispatch.helplist(None, None, **pycompat.strkwargs(opts)))
    elif name:
        rst = dispatch.dispatch(name)
    else:
        rst = dispatch.helphome()

    return "".join(rst)


def formattedhelp(ui, commands, name, keep=None, unknowncmd=False, full=True, **opts):
    """get help for a given topic (as a dotted name) as rendered rst

    Either returns the rendered help text or raises an exception.
    """
    if keep is None:
        keep = []
    else:
        keep = list(keep)  # make a copy so we can mutate this later
    fullname = name
    section = None
    subtopic = None
    if name and "." in name:
        name, remaining = name.split(".", 1)
        remaining = encoding.lower(remaining)
        if "." in remaining:
            subtopic, section = remaining.split(".", 1)
        else:
            if name in subtopics:
                subtopic = remaining
            else:
                section = remaining
    textwidth = ui.configint("ui", "textwidth")
    termwidth = ui.termwidth() - 2
    if textwidth <= 0 or termwidth < textwidth:
        textwidth = termwidth
    text = help_(
        ui, commands, name, subtopic=subtopic, unknowncmd=unknowncmd, full=full, **opts
    )

    formatted, pruned = minirst.format(text, textwidth, keep=keep, section=section)

    # We could have been given a weird ".foo" section without a name
    # to look for, or we could have simply failed to found "foo.bar"
    # because bar isn't a section of foo
    if section and not (formatted and name):
        raise error.Abort(_("help section not found: %s") % fullname)

    if "verbose" in pruned:
        keep.append("omitted")
    else:
        keep.append("notomitted")
    formatted, pruned = minirst.format(text, textwidth, keep=keep, section=section)
    return formatted
