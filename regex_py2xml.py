#!/usr/bin/env python
# ======================================================================
# Copyright (c) 2017 Cisco CVG (Cloud and Virtualization Group)
# All rights reserved.
# See LICENSE file for licensing details
#
# Contributors:
#   Jan Lindblad, jlindbla@cisco.com
# ======================================================================
# regex_py2xml.py
#
# Translator of Python Regular Expressions (the Python re module)
# to XML Schema Regular Expressions, defined by the W3C
# (https://www.w3.org/TR/2004/REC-xmlschema-2-20041028/#regexs)
# ======================================================================
# TODO: The caret (^) and dollar ($) anchors are not properly
# handled in the current version of the translator. They are simply
# removed and ignored. This may or may not be what you want.

import sre_parse
import sys

logging = False

def main():
	for arg in sys.argv[1:]:
		xmlre = translate(arg)
		if logging:
			print "%s  ==>" % arg
		print xmlre

def translate(pyre):
	return "".join(collect(sre_parse.parse(pyre)))

def error(str):
	print "*** ERROR: %s" % str
	sys.exit(1)

def warning(str):
	print "*** Warning: %s" % str

def log(str, indent=0):
	if logging:
		print "%s%s" % (indent*" ", str)

def collect(body, depth=0):
	inner = []
	for subinstr in body:
		inner += generate(subinstr, depth+1)
	return inner

def generate(instr, depth):
	if isinstance(instr, tuple):
		key = instr[0]
		if 'at' == key:
			log("at %s" % instr[1], depth)
			return ""
		elif 'max_repeat' == key:
			rmin, rmax = instr[1][0], instr[1][1]
			body = instr[1][2]
			log("max_repeat %s %s" % (rmin, rmax), depth)
			inner = "".join(collect(body, depth))
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
			return "(" + "".join(collect(body, depth)) + ")"
		elif 'branch' == key:
			body = instr[1][1]
			log("branch %s" % str(instr[1][0]), depth)
			inner = []
			for branch in body:
				log("", depth)
				inner += ["".join(collect(branch, depth))]
			return "|".join(inner)
		elif 'in' == key:
			body = instr[1]
			log("in %s" % len(body), depth)
			return "[" + "".join(collect(body, depth)) + "]"
		elif 'literal' == key:
			char = instr[1]
			log("literal %s" % str(char), depth)
			return "%c" % char
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
				error("Unhandled character category: %s" % cat_name)
		elif 'assert_not' == key:
			assertion = str(instr[1])
			warning("Assertion ignored: %s" % str(assertion))
			return ""

		elif 'TOP' == key:
			body = instr[1]
			log("TOP %s" % len(body), depth)
			return "".join(collect(body, depth))

		else:
			error("Unhandled tuple instr: %s len %s" % (instr[0], len(instr)))
			return "#ERROR#"
	else:
		error("Unhandled instr: %s" % instr)
		return "#ERROR#"

cat_dict = {
	"category_digit":				"\d",
	"category_not_digit":			"\D",
	"category_space":				"\s",
	"category_not_space":			"\S",
	"category_word":				"\w",
	"category_not_word":			"\W",
	"category_linebreak":			"[\n\r]",
	"category_not_linebreak":		".",
	#"category_loc_word":			"#ERROR#", # FIXME: What is this?
	#"category_loc_not_word":		"#ERROR#", # FIXME: What is this?
	"category_uni_digit":			"\d",
	"category_uni_not_digit":		"\D",
	"category_uni_space":			"\s",
	"category_uni_not_space":		"\S",
	"category_uni_word":			"\w",
	"category_uni_not_word":		"\W",
	"category_uni_linebreak":		"[\n\r]",
	"category_uni_not_linebreak":	"."
}

def test():
	assert translate("foo|^([01])") == "foo|([01])"
	assert translate("^([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])+(?:,([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5]))*$") == "([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])+(,([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5]))*"
	assert translate("((unknown|regular|extended|route-target|rd):((unknown:.*:(0*(?:6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])$))|(as2-nn2:(0*(?:6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])):(0*(?:6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])$))|(as4-nn2:(0*(?:429496729[0-5]|42949672[0-8]\d|4294967[01]\d{2}|429496[0-6]\d{3}|42949[0-5]\d{4}|4294[0-8]\d{5}|429[0-3]\d{6}|42[0-8]\d{7}|4[01]\d{8}|[1-3]\d{9}|[1-9]\d{8}|[1-9]\d{7}|[1-9]\d{6}|[1-9]\d{5}|[1-9]\d{4}|[1-9]\d{3}|[1-9]\d{2}|[1-9]\d|\d)):(0*(?:6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])$))|(ipv4-nn2:((?:(?:1\d?\d|[1-9]?\d|2[0-4]\d|25[0-5])\.){3}(?:1\d?\d|[1-9]?\d|2[0-4]\d|25[0-5])):(0*(?:6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9]))))$)") == "((unknown|regular|extended|route-target|rd):((unknown:.*:(0*(6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])))|(as2-nn2:(0*(6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])):(0*(6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])))|(as4-nn2:(0*(429496729[0-5]|42949672[0-8][\d]|4294967[01][\d]{2}|429496[0-6][\d]{3}|42949[0-5][\d]{4}|4294[0-8][\d]{5}|429[0-3][\d]{6}|42[0-8][\d]{7}|4[01][\d]{8}|[1-3][\d]{9}|[1-9][\d]{8}|[1-9][\d]{7}|[1-9][\d]{6}|[1-9][\d]{5}|[1-9][\d]{4}|[1-9][\d]{3}|[1-9][\d]{2}|[1-9][\d]|[\d])):(0*(6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])))|(ipv4-nn2:(((1[\d]?[\d]|[1-9]?[\d]|2[0-4][\d]|25[0-5]).){3}(1[\d]?[\d]|[1-9]?[\d]|2[0-4][\d]|25[0-5])):(0*(6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])))))"

if __name__ == "__main__":
	main()
