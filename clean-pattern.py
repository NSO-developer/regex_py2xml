"""clean-pattern.py is a PYANG plugin that 
detects Python/Perl regex patterns in YANG
modules, and proposes a translation to the
XML Schema regex variant used in YANG.
"""

import optparse
import sys
import os.path
import sre_parse
from pyang import plugin
from pyang import error

clean_pattern_trace = True

def pyang_plugin_init():
    plugin.register_plugin(CleanPatternPlugin())

class CleanPatternPlugin(plugin.PyangPlugin):
    def add_opts(self, optparser):
        optlist = [
            optparse.make_option("--clean-pattern-target",
                                 dest="clean_pattern_target",
                                 help="Output file name, "\
                                 "no repair if not specified"),
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
                raise error.EmitError("%s contains more fundamental errors "\
                    "than the pattern statements" % epos.top.arg)
        emit_clean_pattern(ctx, modules, fd)
        
def emit_clean_pattern(ctx, modules, fd):
    hunt_patterns(modules)

def hunt_patterns(stmts):
    for stmt in stmts:
        if 'pattern' == stmt.keyword:
            orig_pattern = stmt.arg
            log("%s: Parsing pattern '%s'"%(stmt.pos, orig_pattern),)
            patterns = translate(stmt.pos, orig_pattern)
            # Translation will sometimes generate multiple successive .*
            # patterns, which can be simplified with a single .*
            for i in xrange(len(patterns)):
                while ".*.*" in patterns[i]:
                    patterns[i] = patterns[i].replace(".*.*", ".*")
            if len(patterns) == 1 and patterns[0] == orig_pattern:
                # Translation yields the original string, 
                # so let's not talk about this pattern
                pass
            else:
                confidence_str = get_confidence_str(orig_pattern)

                print "%s: Found what is %s a Python/Perl regex:" %\
                    (stmt.pos, confidence_str)
                print "    pattern '%s'"%stmt.arg
                print "    If it is, this is how I would translate it"\
                      " to YANG pattern statements:"
                invert = ""
                for pat in patterns:
                    print "    pattern '%s'%s"%(pat, invert)
                    invert = " { modifier invert-match; }"
        if stmt.substmts:
            hunt_patterns(stmt.substmts)

def get_confidence_str(pattern):
    if pattern[0] == '^' or pattern [-1] == '$':
        return "very likely"
    if '(?:' in pattern or '(?!' in pattern:
        return "likely"
    if pattern.count("^") > pattern.count("[^"):
        return "probably"
    if '\p' in pattern:
        return "probably not"
    return "possibly"

def translate(fileline, pyre):
    parse_tree = sre_parse.parse(pyre)
    patterns = []
    max_negative = 0
    while max_negative < 5:
        log("Starting tree walk with max_negative=%s"%max_negative)
        (fragments, _anchors, _hit_neg) = \
            collect(fileline, [('TOP', (None, [parse_tree]))], max_negative=max_negative)
        if not fragments:
            break
        patterns += ["".join(fragments)]
        max_negative += 1
    return patterns

def logerror(fileline, str):
    print "%s: ERROR: %s" % (fileline, str)
    sys.exit(1)

def logwarning(fileline, str):
    print "%s: Warning: %s" % (fileline, str)

def log(str, indent=0):
    if clean_pattern_trace:
        print "%02s... %s%s" % (indent, indent*" ", str)

def collect(fileline, body, depth=0, head_flex=True, tail_flex=True, max_negative=0):
    inner = []
    head_anchor = tail_anchor = False
    for index in xrange(len(body)):
        subnode = body[index]
        is_first = (0 == index)
        is_last  = (len(body)-1 == index)
        neg_hit = False
        result = generate(fileline, subnode, depth+1, \
            is_first and head_flex, 
            is_last  and tail_flex,
            max_negative)
        # result is either a string (xml schema regex pattern)
        # or a tuple with found string and anchors, (pattern, (head, tail))
        if isinstance(result, tuple): # anchor tuple
            (fragment, (result_head_anchor, result_tail_anchor), neg_hit) = result
            head_anchor = max(head_anchor, result_head_anchor)
            tail_anchor = max(tail_anchor, result_tail_anchor)
        else: # fragment string
            fragment = result
        inner += fragment
        if neg_hit:
            log("neg hit, breaking", depth)
            break
    return (inner, (head_anchor, tail_anchor), neg_hit)

def generate(fileline, node, depth, head_flex, tail_flex, max_negative):
    if isinstance(node, tuple):
        key = node[0]
        if 'at' == key:
            position = node[1]
            log("at %s" % position, depth)
            if "at_beginning" == position:
                return ("", (True, False), False) # anchor at beginning: ^
            return ("", (False, True), False)     # anchor at end      : $
        elif 'max_repeat' == key:
            rmin, rmax = node[1][0], node[1][1]
            body = node[1][2]
            log("max_repeat %s %s" % (rmin, rmax), depth)
            if rmax > 1:
                head_flex = tail_flex = False
            (fragments, (head_anchor, tail_anchor), neg_hit) = \
                collect(fileline, body, depth, head_flex, tail_flex, max_negative)
            if (head_anchor or tail_anchor) and rmax > 1:
                logwarning(fileline, "Using an anchor (^$) inside a "\
                    "repetition group which allows more than one repetition "\
                    "will probably not match what you expect. Translating "\
                    "as if anchor was outside repetition group.")
            inner = "".join(fragments)
            if rmin == 0 and rmax == 1:
                return (inner + "?", (head_anchor, tail_anchor), neg_hit)
            if rmin == 0 and rmax == 4294967295:
                return (inner + "*", (head_anchor, tail_anchor), neg_hit)
            if rmin == 1 and rmax == 4294967295:
                return (inner + "+", (head_anchor, tail_anchor), neg_hit)
            if rmin == rmax:
                return (inner + "{%s}" % rmin, (head_anchor, tail_anchor), neg_hit)
            return (inner + "{%s,%s}" % (rmin, rmax), (head_anchor, tail_anchor), neg_hit)
        elif 'subpattern' == key:
            body = node[1][1]
            log("subpattern %s" % node[1][0], depth)
            #log("aaa %s"%((head_flex, tail_flex),), depth)
            (fragments, anchors, neg_hit) = collect(fileline, body, depth, head_flex, tail_flex, max_negative)
            #log("bbb %s"%(anchors,), depth)
            if len(body) == 1 and body[0][0] != 'branch':
                # A subpattern with a single element is redundant
                return ("".join(fragments), anchors, neg_hit)
            return ("(" + "".join(fragments) + ")", anchors, neg_hit)
        elif 'branch' == key or 'TOP' == key:
            body = node[1][1]
            log("branch %s" % str(node[1][0]), depth)
            inner = []
            neg_hit = head_anchor = tail_anchor = False
            for branch in body:
                log("", depth) # Empty line in between branch alternatives
                (fragments, (result_head_anchor, result_tail_anchor), result_neg_hit) = \
                    collect(fileline, branch, depth, head_flex, tail_flex, max_negative)
                result = "".join(fragments)
                if head_flex and not result_head_anchor:
                    result = ".*" + result
                if tail_flex and not result_tail_anchor:
                    result += ".*"
                if 0 == max_negative or result_neg_hit:
                    inner += [result]
                neg_hit = max(neg_hit, result_neg_hit)
                head_anchor = max(head_anchor, result_head_anchor)
                tail_anchor = max(tail_anchor, result_tail_anchor)
            return ("|".join(inner), (head_anchor, tail_anchor), neg_hit)
        elif 'in' == key:
            body = node[1]
            log("in %s" % len(body), depth)
            (fragments, anchors, neg_hit) = collect(fileline, body, depth, head_flex, tail_flex, max_negative)
            if len(body) == 1 and 'category' == body[0][0]:
                # 'in' with single category as arg can be represented 
                # without the []
                return "".join(fragments)
            return "[" + "".join(fragments) + "]"
        elif 'literal' == key:
            char = node[1]
            log("literal %s" % str(char), depth)
            if ("%c" % char) in "\\|.^?*+{}()[]": 
                return "\%c" % char
            return "%c" % char
        elif 'not_literal' == key:
            char = node[1]
            log("not_literal %s" % str(char), depth)
            if ("%c" % char) in "\\|.^?*+{}()[]": 
                return "[^\%c]" % char
            return "[^%c]" % char
        elif 'range' == key:
            fromchar, tochar = node[1][0], node[1][1]
            log("range %s-%s" % (fromchar, tochar), depth)
            return "%c-%c"%(fromchar, tochar)
        elif 'negate' == key:
            log("negate", depth)
            return "^"
        elif 'any' == key:
            log("any", depth)
            return "."
        elif 'category' == key:
            cat_name = node[1]
            log("category %s" % cat_name, depth)
            try: 
                return cat_dict[cat_name]
            except:
                logerror(fileline, "Parsing failed, unknown character category: %s" % cat_name)
        elif 'assert_not' == key:
            body = node[1][1]
            length = node[1][0]
            if 1 != max_negative:
                log("assert_not %s skipped in current run" % length, depth)
                return ""
            log("assert_not %s in negative pattern" % length, depth)
            (fragments, anchors, neg_hit) = collect(fileline, body, depth, head_flex, tail_flex, max_negative-1)

            if len(body) == 1 and body[0][0] != 'branch':
                # A subpattern with a single element is redundant
                return ("".join(fragments), anchors, True)
            return ("".join(fragments), anchors, True)
        else:
            logerror(fileline, "Parsing failed, unknown tuple node: %s len %s" % (node[0], len(node)))
            return "#ERROR#"
    else:
        logerror(fileline, "Parsing failed, unknown node: %s" % node)
        return "#ERROR#"

cat_dict = {
    "category_digit":               "\d",
    "category_not_digit":           "\D",
    "category_space":               "\s",
    "category_not_space":           "\S",
    "category_word":                "\w",
    "category_not_word":            "\W",
    "category_linebreak":           "[\\n\\r]",
    "category_not_linebreak":       ".",
    #"category_loc_word":           "#ERROR#", # FIXME: What is this?
    #"category_loc_not_word":       "#ERROR#", # FIXME: What is this?
    "category_uni_digit":           "\d",
    "category_uni_not_digit":       "\D",
    "category_uni_space":           "\s",
    "category_uni_not_space":       "\S",
    "category_uni_word":            "\w",
    "category_uni_not_word":        "\W",
    "category_uni_linebreak":       "[\\n\\r]",
    "category_uni_not_linebreak":   "."
}
