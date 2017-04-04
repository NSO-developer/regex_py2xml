"""clean-pattern.py is a PYANG plugin that 
checks and repairs YANG pattern statements
"""

import optparse
import sys
import os.path
import sre_parse
from pyang import plugin
from pyang import error

clean_pattern_trace = False

def pyang_plugin_init():
    plugin.register_plugin(CleanPatternPlugin())

class CleanPatternPlugin(plugin.PyangPlugin):
    def add_opts(self, optparser):
        optlist = [
            optparse.make_option("--clean-pattern-target",
                                 dest="clean_pattern_target",
                                 help="Output file name, no repair if not specified"),
            optparse.make_option("--clean-pattern-trace",
                                 dest="clean_pattern_trace",
                                 help="Trace regex parsing"),
            ]
        g = optparser.add_option_group("Clean-pattern output specific options")
        g.add_options(optlist)
    def add_output_format(self, fmts):
        self.multiple_modules = True
        fmts['clean-pattern'] = self
    def emit(self, ctx, modules, fd):
        # cannot do this unless everything is ok for our module
        modulenames = [m.arg for m in modules]
        for (epos, etag, eargs) in ctx.errors:
            if ((epos.top is None or epos.top.arg in modulenames) and
                error.is_error(error.err_level(etag))):
                raise error.EmitError("%s contains more fundamental errors than the pattern statements" % epos.top.arg)
        emit_clean_pattern(ctx, modules, fd)

        
def emit_clean_pattern(ctx, modules, fd):
        hunt_patterns(modules)
        fd.write('\n')

def hunt_patterns(stmts):
    for stmt in stmts:
        pos = ""
        if hasattr(stmt.i_module, 'pos'):
            pos = stmt.pos
            #print "... %s: %s"% (pos, stmt.keyword)
        if 'pattern' == stmt.keyword:
            #prereqs = stmt.search("pattern")
            #print "=== Found pattern: %s" % stmt.arg
            print stmt.pos
            new_pattern = translate(stmt.arg)
            while ".*.*" in new_pattern:
                new_pattern = new_pattern.replace(".*.*", ".*")
            if new_pattern == stmt.arg:
                # (?: 
                # (?!
                # ^ (except [^)
                # $

                # \p
                print "---> ok"
            else:
                print "---> suggest changing from:"
                print stmt.arg
                print "to:"
                print new_pattern
        if stmt.substmts:
            hunt_patterns(stmt.substmts)

def translate(pyre):
    parse_tree = sre_parse.parse(pyre)
    (fragments, _anchors) = collect([('TOP', (None, [parse_tree]))])
    return "".join(fragments)

def logerror(str):
    print "*** ERROR: %s" % str
    sys.exit(1)

def logwarning(str):
    print "*** Warning: %s" % str

def log(str, indent=0):
    if clean_pattern_trace:
        print "... %s%s" % (indent*" ", str)

def collect(body, depth=0, head_flex=True, tail_flex=True, is_branch=False):
    inner = []
    head_anchor = tail_anchor = False
    for index in xrange(len(body)):
        subinstr = body[index]
        is_first = (0 == index)
        is_last  = (len(body)-1 == index)
        result = generate(subinstr, depth+1, \
            (is_branch or is_first) and head_flex, 
            (is_branch or is_last ) and tail_flex)
        # result is either a string (xml schema regex pattern)
        # or a tuple with found anchors, (head, tail)
        if isinstance(result, tuple): # anchor tuple
            (fragment, (result_head_anchor, result_tail_anchor)) = result
            head_anchor = max(head_anchor, result_head_anchor)
            tail_anchor = max(tail_anchor, result_tail_anchor)
        else: # fragment string
            fragment = result
        inner += fragment
    log("cnc %s"%((head_anchor, tail_anchor),), depth)
    return (inner, (head_anchor, tail_anchor))

def generate(instr, depth, head_flex, tail_flex):
    #print "gen %s %s"%(head_flex, tail_flex)
    #print "### %s"%(instr,)
    if isinstance(instr, tuple):
        key = instr[0]
        if 'at' == key:
            position = instr[1]
            log("at %s" % position, depth)
            if "at_beginning" == position:
                return ("", (True, False)) # anchor at beginning: ^
            return ("", (False, True))     # anchor at end      : $
        elif 'max_repeat' == key:
            rmin, rmax = instr[1][0], instr[1][1]
            body = instr[1][2]
            log("max_repeat %s %s" % (rmin, rmax), depth)
            (fragments, _anchors) = collect(body, depth, head_flex, tail_flex)
            inner = "".join(fragments)
            if rmin == 0 and rmax == 1:
                return inner + "?"
            if rmin == 0 and rmax == 4294967295:
                return inner + "*"
            if rmin == 1 and rmax == 4294967295:
                return inner + "+"
            if rmin == rmax:
                return inner + "{%s}" % rmin
            return inner + "{%s,%s}" % (rmin, rmax)
        elif 'subpattern' == key:
            body = instr[1][1]
            log("subpattern %s" % instr[1][0], depth)
            (fragments, anchors) = collect(body, depth, head_flex, tail_flex)
            #print "anc %s"%(anchors,)
            return ("(" + "".join(fragments) + ")", anchors)
        elif 'branch' == key or 'TOP' == key:
            body = instr[1][1]
            log("branch %s" % str(instr[1][0]), depth)
            inner = []
            head_anchor = tail_anchor = False
            for branch in body:
                log("", depth)
                (fragments, (result_head_anchor, result_tail_anchor)) = collect(branch, depth, head_flex, tail_flex, False)
                #print "dnc %s"%((result_head_anchor, result_tail_anchor),)
                result = "".join(fragments)
                #print "xxx %s %s"%(head_flex, tail_flex)
                if head_flex and not result_head_anchor:
                    result = ".*" + result
                if tail_flex and not result_tail_anchor:
                    result += ".*"
                inner += [result]
                head_anchor = max(head_anchor, result_head_anchor)
                tail_anchor = max(tail_anchor, result_tail_anchor)
            #print "bnc %s"%((head_anchor, tail_anchor),)
            return ("|".join(inner), (head_anchor, tail_anchor))
        elif 'in' == key:
            body = instr[1]
            log("in %s" % len(body), depth)
            # FIXME: 'in' with single literal as arg can be represented without the []
            (fragments, anchors) = collect(body, depth, head_flex, tail_flex)
            return "[" + "".join(fragments) + "]"
        elif 'literal' == key:
            char = instr[1]
            log("literal %s" % str(char), depth)
            if ("%c" % char) in "\\|.^?*+{}()[]": 
                return "\%c" % char
            return "%c" % char
        elif 'not_literal' == key:
            char = instr[1]
            log("not_literal %s" % str(char), depth)
            if ("%c" % char) in "\\|.^?*+{}()[]": 
                return "[^\%c]" % char
            return "[^%c]" % char
        elif 'range' == key:
            fromchar, tochar = instr[1][0], instr[1][1]
            log("range %s-%s" % (fromchar, tochar), depth)
            return "%c-%c"%(fromchar, tochar)
        elif 'negate' == key:
            log("negate", depth)
            return "^"
        elif 'any' == key:
            log("any", depth)
            return "."
        elif 'category' == key:
            cat_name = instr[1]
            log("category %s" % cat_name, depth)
            try: 
                return cat_dict[cat_name]
            except:
                logerror("Unhandled character category: %s" % cat_name)
        elif 'assert_not' == key:
            assertion = str(instr[1])
            logwarning("Assertion ignored: %s" % str(assertion))
            return ""

        elif 'TOP' == key:
            body = instr[1]
            log("TOP %s" % len(body), depth)
            (fragments, anchors) = collect(body, depth, head_flex, tail_flex)
            return "".join(fragments)

        else:
            logerror("Unhandled tuple instr: %s len %s" % (instr[0], len(instr)))
            return "#ERROR#"
    else:
        logerror("Unhandled instr: %s" % instr)
        return "#ERROR#"

cat_dict = {
    "category_digit":               "\d",
    "category_not_digit":           "\D",
    "category_space":               "\s",
    "category_not_space":           "\S",
    "category_word":                "\w",
    "category_not_word":            "\W",
    "category_linebreak":           "[\n\r]",
    "category_not_linebreak":       ".",
    #"category_loc_word":           "#ERROR#", # FIXME: What is this?
    #"category_loc_not_word":       "#ERROR#", # FIXME: What is this?
    "category_uni_digit":           "\d",
    "category_uni_not_digit":       "\D",
    "category_uni_space":           "\s",
    "category_uni_not_space":       "\S",
    "category_uni_word":            "\w",
    "category_uni_not_word":        "\W",
    "category_uni_linebreak":       "[\n\r]",
    "category_uni_not_linebreak":   "."
}
