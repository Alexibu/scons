
"""SCons.Tool.docbook

Tool-specific initialization for Docbook.

There normally shouldn't be any need to import this module directly.
It will usually be imported through the generic SCons.Tool.Tool()
selection method.

"""

#
# Copyright (c) 2001-7,2010 The SCons Foundation
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import os
import glob
import re

import SCons.Action
import SCons.Builder
import SCons.Defaults
import SCons.Script
import SCons.Tool
import SCons.Util

# Get full path to this script
scriptpath = os.path.dirname(os.path.realpath(__file__))

# Local folder for the collection of DocBook XSLs
db_xsl_folder = 'docbook-xsl-1.76.1'

# Do we have libxml2/libxslt/lxml?
has_libxml2 = True
has_lxml = True
try:
    import libxml2
    import libxslt
except:
    has_libxml2 = False
try:
    import lxml
except:
    has_lxml = False

# Set this to True, to prefer xsltproc over libxml2 and lxml
prefer_xsltproc = False

# Regexs for parsing Docbook XML sources of MAN pages
re_manvolnum = re.compile("<manvolnum>([^<]*)</manvolnum>")
re_refname = re.compile("<refname>([^<]*)</refname>")

#
# Helper functions
#
def __extend_targets_sources(target, source):
    """ Prepare the lists of target and source files. """
    if not SCons.Util.is_List(target):
        target = [target]
    if not source:
        source = target[:]
    elif not SCons.Util.is_List(source):
        source = [source]
    if len(target) < len(source):
        target.extend(source[len(target):])
        
    return target, source

def __init_xsl_stylesheet(kw, env, user_xsl_var, default_path):
    if kw.get('DOCBOOK_XSL','') == '':
        xsl_style = kw.get('xsl', env.subst(user_xsl_var))
        if xsl_style == '':
            path_args = [scriptpath, db_xsl_folder] + default_path
            xsl_style = os.path.join(*path_args)
        kw['DOCBOOK_XSL'] =  xsl_style
    
def __select_builder(lxml_builder, libxml2_builder, cmdline_builder):
    """ Selects a builder, based on which Python modules are present. """
    if prefer_xsltproc:
        return cmdline_builder
    
    if not has_libxml2:
        # At the moment we prefer libxml2 over lxml, the latter can lead
        # to conflicts when installed together with libxml2.
        if has_lxml:
            return lxml_builder
        else:
            return cmdline_builder

    return libxml2_builder

def __ensure_suffix(t, suffix):
    """ Ensure that the target t has the given suffix. """
    tpath = str(t)
    if not tpath.endswith(suffix):
        return tpath+suffix
    
    return t

def __ensure_suffix_stem(t, suffix):
    """ Ensure that the target t has the given suffix, and return the file's stem. """
    tpath = str(t)
    if not tpath.endswith(suffix):
        stem = tpath
        tpath += suffix
        
        return tpath, stem
    else:
        stem, ext = os.path.splitext(tpath)
    
    return t, stem

def __get_xml_text(root):
    """ Return the text for the given root node (xml.dom.minidom). """
    txt = ""
    for e in root.childNodes:
        if (e.nodeType == e.TEXT_NODE):
            txt += e.data
    return txt

def __create_output_dir(base_dir):
    """ Ensure that the output directory base_dir exists. """
    root, tail = os.path.split(base_dir)
    dir = None
    if tail:
        if base_dir.endswith('/'):
            dir = base_dir
        else:
            dir = root
    else:
        if base_dir.endswith('/'):
            dir = base_dir
    
    if dir and not os.path.isdir(dir):
        os.makedirs(dir)


#
# Supported command line tools and their call "signature"
#
xsltproc_com = {'xsltproc' : '$DOCBOOK_XSLTPROC $DOCBOOK_XSLTPROCFLAGS -o $TARGET $DOCBOOK_XSL $SOURCE',
                'saxon' : '$DOCBOOK_XSLTPROC $DOCBOOK_XSLTPROCFLAGS -o $TARGET $DOCBOOK_XSL $SOURCE $DOCBOOK_XSLTPROCPARAMS',
                'saxon-xslt' : '$DOCBOOK_XSLTPROC $DOCBOOK_XSLTPROCFLAGS -o $TARGET $DOCBOOK_XSL $SOURCE $DOCBOOK_XSLTPROCPARAMS',
                'xalan' : '$DOCBOOK_XSLTPROC $DOCBOOK_XSLTPROCFLAGS -q -out $TARGET -xsl $DOCBOOK_XSL -in $SOURCE'}
xmllint_com = {'xmllint' : '$DOCBOOK_XMLLINT $DOCBOOK_XMLLINTFLAGS --xinclude $SOURCE > $TARGET'}
fop_com = {'fop' : '$DOCBOOK_FOP $DOCBOOK_FOPFLAGS -fo $SOURCE -pdf $TARGET',
           'xep' : '$DOCBOOK_FOP $DOCBOOK_FOPFLAGS -o $TARGET $SOURCE',
           'jw' : '$DOCBOOK_FOP $DOCBOOK_FOPFLAGS -f docbook -b pdf $SOURCE -o $TARGET'}

def __detect_cl_tool(env, chainkey, cdict):
    """
    Helper function, picks a command line tool from the list
    and initializes its environment variables.
    """
    if env.get(chainkey,'') == '':
        clpath = ''
        for cltool in cdict:
            clpath = env.WhereIs(cltool)
            if clpath:
                env[chainkey] = clpath
                if not env[chainkey + 'COM']:
                    env[chainkey + 'COM'] = cdict[cltool]

def _detect(env):
    """
    Detect all the command line tools that we might need for creating
    the requested output formats.
    """
    global prefer_xsltproc
    
    if env.get('DOCBOOK_PREFER_XSLTPROC',''):
        prefer_xsltproc = True
        
    if ((not has_libxml2 and not has_lxml) or (prefer_xsltproc)):
        # Try to find the XSLT processors
        __detect_cl_tool(env, 'DOCBOOK_XSLTPROC', xsltproc_com)
        __detect_cl_tool(env, 'DOCBOOK_XMLLINT', xmllint_com)

    __detect_cl_tool(env, 'DOCBOOK_FOP', fop_com)

#
# Scanners
#
include_re = re.compile('fileref\\s*=\\s*["|\']([^\\n]*)["|\']')
sentity_re = re.compile('<!ENTITY\\s+%*\\s*[^\\s]+\\s+SYSTEM\\s+["|\']([^\\n]*)["|\']>')
 
def __xml_scan(node, env, path, arg):
    """ Simple XML file scanner, detecting local images and XIncludes as implicit dependencies. """
    # Does the node exist yet?
    if not os.path.isfile(str(node)):
        return []
    
    if env.get('DOCBOOK_SCANENT',''):
        # Use simple pattern matching for system entities..., no support 
        # for recursion yet.
        contents = node.get_text_contents()
        return sentity_re.findall(contents)

    xsl_file = os.path.join(scriptpath,'utils','xmldepend.xsl')
    if not has_libxml2 or prefer_xsltproc:
        if has_lxml and not prefer_xsltproc:
            
            from lxml import etree
            
            xsl_tree = etree.parse(xsl_file)
            doc = etree.parse(str(node))
            result = doc.xslt(xsl_tree)

            depfiles = [x.strip() for x in str(result).splitlines() if x.strip() != "" and not x.startswith("<?xml ")]
            return depfiles
        else:
            # Try to call xsltproc
            xsltproc = env.subst("$DOCBOOK_XSLTPROC")
            if xsltproc and xsltproc.endswith('xsltproc'):
                result = env.backtick(' '.join([xsltproc, xsl_file, str(node)]))
                depfiles = [x.strip() for x in str(result).splitlines() if x.strip() != "" and not x.startswith("<?xml ")]
                return depfiles
            else:
                # Use simple pattern matching, there is currently no support
                # for xi:includes...
                contents = node.get_text_contents()
                return include_re.findall(contents)

    styledoc = libxml2.parseFile(xsl_file)
    style = libxslt.parseStylesheetDoc(styledoc)
    doc = libxml2.parseFile(str(node))
    result = style.applyStylesheet(doc, None)

    depfiles = []
    for x in str(result).splitlines():
        if x.strip() != "" and not x.startswith("<?xml "):
            depfiles.extend(x.strip().split())
    
    style.freeStylesheet()
    doc.freeDoc()
    result.freeDoc()

    return depfiles

# Creating the instance of our XML dependency scanner
docbook_xml_scanner = SCons.Script.Scanner(function = __xml_scan,
                                           argument = None)

#
# Builders
#
def __build_libxml2(target, source, env):
    """
    General XSLT builder (HTML/FO), using the libxml2 module.
    """
    xsl_style = env.subst('$DOCBOOK_XSL')
    styledoc = libxml2.parseFile(xsl_style)
    style = libxslt.parseStylesheetDoc(styledoc)
    doc = libxml2.readFile(str(source[0]),None,libxml2.XML_PARSE_NOENT)
    # Support for additional parameters
    parampass = {}
    if parampass:
        result = style.applyStylesheet(doc, parampass)
    else:
        result = style.applyStylesheet(doc, None)
    style.saveResultToFilename(str(target[0]), result, 0)
    style.freeStylesheet()
    doc.freeDoc()
    result.freeDoc()

    return None

def __build_lxml(target, source, env):
    """
    General XSLT builder (HTML/FO), using the lxml module.
    """
    from lxml import etree
    
    xsl_style = env.subst('$DOCBOOK_XSL')
    xsl_tree = etree.parse(xsl_style)
    doc = etree.parse(str(source[0]))
    # Support for additional parameters
    parampass = {}
    if parampass:
        result = doc.xslt(xsl_tree, *parampass)
    else:
        result = doc.xslt(xsl_tree)
        
    result.write(str(target[0]), pretty_print=True)

    return None

def __xinclude_libxml2(target, source, env):
    """
    Resolving XIncludes, using the libxml2 module.
    """
    doc = libxml2.readFile(str(source[0]), None, libxml2.XML_PARSE_NOENT)
    doc.xincludeProcess()
    doc.saveFile(str(target[0]))
    doc.freeDoc()

    return None

def __xinclude_lxml(target, source, env):
    """
    Resolving XIncludes, using the lxml module.
    """
    from lxml import etree
    
    doc = etree.parse(str(source[0]))
    doc.xinclude()
    try:
        of = open(str(target[0]), 'w')
        of.write(str(doc))
        of.close()
    except:
        pass

    return None

__libxml2_builder = SCons.Builder.Builder(
        action = __build_libxml2,
        src_suffix = '.xml',
        source_scanner = docbook_xml_scanner)
__lxml_builder = SCons.Builder.Builder(
        action = __build_lxml,
        src_suffix = '.xml',
        source_scanner = docbook_xml_scanner)

__xinclude_libxml2_builder = SCons.Builder.Builder(
        action = __xinclude_libxml2,
        suffix = '.xml',
        src_suffix = '.xml',
        source_scanner = docbook_xml_scanner)
__xinclude_lxml_builder = SCons.Builder.Builder(
        action = __xinclude_lxml,
        suffix = '.xml',
        src_suffix = '.xml',
        source_scanner = docbook_xml_scanner)

__xsltproc_builder = SCons.Builder.Builder(
        action = SCons.Action.Action('$DOCBOOK_XSLTPROCCOM','$DOCBOOK_XSLTPROCCOMSTR'),
        src_suffix = '.xml',
        source_scanner = docbook_xml_scanner)
__xmllint_builder = SCons.Builder.Builder(
        action = SCons.Action.Action('$DOCBOOK_XMLLINTCOM','$DOCBOOK_XMLLINTCOMSTR'),
        suffix = '.xml',
        src_suffix = '.xml',
        source_scanner = docbook_xml_scanner)
__fop_builder = SCons.Builder.Builder(
        action = SCons.Action.Action('$DOCBOOK_FOPCOM','$DOCBOOK_FOPCOMSTR'),
        suffix = '.pdf',
        src_suffix = '.fo',
        ensure_suffix=1)

def DocbookHtml(env, target, source=None, *args, **kw):
    """
    A pseudo-Builder, providing a Docbook toolchain for HTML output.
    """
    # Init list of targets/sources
    target, source = __extend_targets_sources(target, source)
    
    # Init XSL stylesheet
    __init_xsl_stylesheet(kw, env, '$DOCBOOK_DEFAULT_XSL_HTML', ['html','docbook.xsl'])

    # Setup builder
    __builder = __select_builder(__lxml_builder, __libxml2_builder, __xsltproc_builder)
    
    # Create targets
    result = []
    for t,s in zip(target,source):
        r = __builder.__call__(env, __ensure_suffix(t,'.html'), s, **kw)
        env.Depends(r, kw['DOCBOOK_XSL'])
        result.extend(r)

    return result

def DocbookHtmlChunked(env, target, source=None, *args, **kw):
    """
    A pseudo-Builder, providing a Docbook toolchain for chunked HTML output.
    """
    # Init target/source
    if not SCons.Util.is_List(target):
        target = [target]
    if not source:
        source = target
        target = ['index.html']
    elif not SCons.Util.is_List(source):
        source = [source]
        
    # Init XSL stylesheet
    __init_xsl_stylesheet(kw, env, '$DOCBOOK_DEFAULT_XSL_HTMLCHUNKED', ['html','chunkfast.xsl'])

    # Setup builder
    __builder = __select_builder(__lxml_builder, __libxml2_builder, __xsltproc_builder)
    
    # Detect base dir
    base_dir = kw.get('base_dir', '')
    if base_dir:
        __create_output_dir(base_dir)
   
    # Create targets
    result = []
    r = __builder.__call__(env, base_dir+__ensure_suffix(str(target[0]), '.html'), source[0], **kw)
    env.Depends(r, kw['DOCBOOK_XSL'])
    result.extend(r)
    # Add supporting files for cleanup
    env.Clean(r, glob.glob(base_dir+'*.html'))

    return result


def DocbookHtmlhelp(env, target, source=None, *args, **kw):
    """
    A pseudo-Builder, providing a Docbook toolchain for HTMLHELP output.
    """
    # Init target/source
    if not SCons.Util.is_List(target):
        target = [target]
    if not source:
        source = target
        target = ['index.html']
    elif not SCons.Util.is_List(source):
        source = [source]    
    
    # Init XSL stylesheet
    __init_xsl_stylesheet(kw, env, '$DOCBOOK_DEFAULT_XSL_HTMLHELP', ['htmlhelp','htmlhelp.xsl'])

    # Setup builder
    __builder = __select_builder(__lxml_builder, __libxml2_builder, __xsltproc_builder)

    # Detect base dir
    base_dir = kw.get('base_dir', '')
    if base_dir:
        __create_output_dir(base_dir)
    
    # Create targets
    result = []
    r = __builder.__call__(env, base_dir+__ensure_suffix(str(target[0]), '.html'), source[0], **kw)
    env.Depends(r, kw['DOCBOOK_XSL'])
    result.extend(r)
    # Add supporting files for cleanup
    env.Clean(r, ['toc.hhc', 'htmlhelp.hhp', 'index.hhk'] +
                 glob.glob(base_dir+'[ar|bk|ch]*.html'))

    return result

def DocbookPdf(env, target, source=None, *args, **kw):
    """
    A pseudo-Builder, providing a Docbook toolchain for PDF output.
    """
    # Init list of targets/sources
    target, source = __extend_targets_sources(target, source)

    # Init XSL stylesheet
    __init_xsl_stylesheet(kw, env, '$DOCBOOK_DEFAULT_XSL_PDF', ['fo','docbook.xsl'])

    # Setup builder
    __builder = __select_builder(__lxml_builder, __libxml2_builder, __xsltproc_builder)

    # Create targets
    result = []
    for t,s in zip(target,source):
        t, stem = __ensure_suffix_stem(t, '.pdf')
        xsl = __builder.__call__(env, stem+'.fo', s, **kw)
        result.extend(xsl)
        env.Depends(xsl, kw['DOCBOOK_XSL'])
        result.extend(__fop_builder.__call__(env, t, xsl, **kw))

    return result

def DocbookMan(env, target, source=None, *args, **kw):
    """
    A pseudo-Builder, providing a Docbook toolchain for Man page output.
    """
    # Init list of targets/sources
    target, source = __extend_targets_sources(target, source)

    # Init XSL stylesheet
    __init_xsl_stylesheet(kw, env, '$DOCBOOK_DEFAULT_XSL_MAN', ['manpages','docbook.xsl'])

    # Setup builder
    __builder = __select_builder(__lxml_builder, __libxml2_builder, __xsltproc_builder)

    # Create targets
    result = []
    for t,s in zip(target,source):
        volnum = "1"
        outfiles = []
        srcfile = __ensure_suffix(str(s),'.xml')
        if os.path.isfile(srcfile):
            try:
                import xml.dom.minidom
                
                dom = xml.dom.minidom.parse(__ensure_suffix(str(s),'.xml'))
                # Extract volume number, default is 1
                for node in dom.getElementsByTagName('refmeta'):
                    for vol in node.getElementsByTagName('manvolnum'):
                        volnum = __get_xml_text(vol)
                        
                # Extract output filenames
                for node in dom.getElementsByTagName('refnamediv'):
                    for ref in node.getElementsByTagName('refname'):
                        outfiles.append(__get_xml_text(ref)+'.'+volnum)
                        
            except:
                # Use simple regex parsing 
                f = open(__ensure_suffix(str(s),'.xml'), 'r')
                content = f.read()
                f.close()
                
                for m in re_manvolnum.finditer(content):
                    volnum = m.group(1)
                    
                for m in re_refname.finditer(content):
                    outfiles.append(m.group(1)+'.'+volnum)
            
            if not outfiles:
                # Use stem of the source file
                spath = str(s)
                if not spath.endswith('.xml'):
                    outfiles.append(spath+'.'+volnum)
                else:
                    stem, ext = os.path.splitext(spath)
                    outfiles.append(stem+'.'+volnum)
        else:
            # We have to completely rely on the given target name
            outfiles.append(t)
            
        __builder.__call__(env, outfiles[0], s, **kw)
        env.Depends(outfiles[0], kw['DOCBOOK_XSL'])
        result.append(outfiles[0])
        if len(outfiles) > 1:
            env.Clean(outfiles[0], outfiles[1:])

        
    return result

def DocbookSlidesPdf(env, target, source=None, *args, **kw):
    """
    A pseudo-Builder, providing a Docbook toolchain for PDF slides output.
    """
    # Init list of targets/sources
    target, source = __extend_targets_sources(target, source)

    # Init XSL stylesheet
    __init_xsl_stylesheet(kw, env, '$DOCBOOK_DEFAULT_XSL_SLIDESPDF', ['slides','fo','plain.xsl'])

    # Setup builder
    __builder = __select_builder(__lxml_builder, __libxml2_builder, __xsltproc_builder)

    # Create targets
    result = []
    for t,s in zip(target,source):
        t, stem = __ensure_suffix_stem(t, '.pdf')
        xsl = __builder.__call__(env, stem+'.fo', s, **kw)
        env.Depends(xsl, kw['DOCBOOK_XSL'])        
        result.extend(xsl)
        result.extend(__fop_builder.__call__(env, t, xsl, **kw))

    return result

def DocbookSlidesHtml(env, target, source=None, *args, **kw):
    """
    A pseudo-Builder, providing a Docbook toolchain for HTML slides output.
    """
    # Init list of targets/sources
    if not SCons.Util.is_List(target):
        target = [target]
    if not source:
        source = target
        target = ['index.html']
    elif not SCons.Util.is_List(source):
        source = [source]    

    # Init XSL stylesheet
    __init_xsl_stylesheet(kw, env, '$DOCBOOK_DEFAULT_XSL_SLIDESHTML', ['slides','html','plain.xsl'])

    # Setup builder
    __builder = __select_builder(__lxml_builder, __libxml2_builder, __xsltproc_builder)

    # Detect base dir
    base_dir = kw.get('base_dir', '')
    if base_dir:
        __create_output_dir(base_dir)

    # Create targets
    result = []
    r = __builder.__call__(env, base_dir+__ensure_suffix(str(target[0]), '.html'), source[0], **kw)
    env.Depends(r, kw['DOCBOOK_XSL'])
    result.extend(r)
    # Add supporting files for cleanup
    env.Clean(r, [base_dir+'toc.html'] +
                 glob.glob(base_dir+'foil*.html'))

    return result

def DocbookXInclude(env, target, source, *args, **kw):
    """
    A pseudo-Builder, for resolving XIncludes in a separate processing step.
    """
    # Init list of targets/sources
    target, source = __extend_targets_sources(target, source)

    # Setup builder
    __builder = __select_builder(__xinclude_lxml_builder,__xinclude_libxml2_builder,__xmllint_builder)
            
    # Create targets
    result = []
    for t,s in zip(target,source):
        result.extend(__builder.__call__(env, t, s, **kw))
        
    return result

def DocbookXslt(env, target, source=None, *args, **kw):
    """
    A pseudo-Builder, applying a simple XSL transformation to the input file.
    """
    # Init list of targets/sources
    target, source = __extend_targets_sources(target, source)
    
    # Init XSL stylesheet
    kw['DOCBOOK_XSL'] = kw.get('xsl', 'transform.xsl')

    # Setup builder
    __builder = __select_builder(__lxml_builder, __libxml2_builder, __xsltproc_builder)
    
    # Create targets
    result = []
    for t,s in zip(target,source):
        r = __builder.__call__(env, t, s, **kw)
        env.Depends(r, kw['DOCBOOK_XSL'])
        result.extend(r)

    return result



def generate(env):
    """Add Builders and construction variables for docbook to an Environment."""

    env.SetDefault(
        # Default names for customized XSL stylesheets
        DOCBOOK_DEFAULT_XSL_HTML = '',        
        DOCBOOK_DEFAULT_XSL_HTMLCHUNKED = '',        
        DOCBOOK_DEFAULT_XSL_HTMLHELP = '',        
        DOCBOOK_DEFAULT_XSL_PDF = '',        
        DOCBOOK_DEFAULT_XSL_MAN = '',        
        DOCBOOK_DEFAULT_XSL_SLIDESPDF = '',        
        DOCBOOK_DEFAULT_XSL_SLIDESHTML = '',        
        
        # Paths to the detected executables
        DOCBOOK_XSLTPROC = '',
        DOCBOOK_XMLLINT = '',
        DOCBOOK_FOP = '',
        
        # Additional flags for the text processors
        DOCBOOK_XSLTPROCFLAGS = SCons.Util.CLVar(''),
        DOCBOOK_XMLLINTFLAGS = SCons.Util.CLVar(''),
        DOCBOOK_FOPFLAGS = SCons.Util.CLVar(''),
        DOCBOOK_XSLTPROCPARAMS = SCons.Util.CLVar(''),
        
        # Default command lines for the detected executables
        DOCBOOK_XSLTPROCCOM = xsltproc_com['xsltproc'],
        DOCBOOK_XMLLINTCOM = xmllint_com['xmllint'],
        DOCBOOK_FOPCOM = fop_com['fop'],

        # Screen output for the text processors
        DOCBOOK_XSLTPROCCOMSTR = None,
        DOCBOOK_XMLLINTCOMSTR = None,
        DOCBOOK_FOPCOMSTR = None,
        
        )
    _detect(env)

    try:
        env.AddMethod(DocbookHtml, "DocbookHtml")
        env.AddMethod(DocbookHtmlChunked, "DocbookHtmlChunked")
        env.AddMethod(DocbookHtmlhelp, "DocbookHtmlhelp")
        env.AddMethod(DocbookPdf, "DocbookPdf")
        env.AddMethod(DocbookMan, "DocbookMan")
        env.AddMethod(DocbookSlidesPdf, "DocbookSlidesPdf")
        env.AddMethod(DocbookSlidesHtml, "DocbookSlidesHtml")
        env.AddMethod(DocbookXInclude, "DocbookXInclude")
        env.AddMethod(DocbookXslt, "DocbookXslt")
    except AttributeError:
        # Looks like we use a pre-0.98 version of SCons...
        from SCons.Script.SConscript import SConsEnvironment
        SConsEnvironment.DocbookHtml = DocbookHtml
        SConsEnvironment.DocbookHtmlChunked = DocbookHtmlChunked
        SConsEnvironment.DocbookHtmlhelp = DocbookHtmlhelp
        SConsEnvironment.DocbookPdf = DocbookPdf
        SConsEnvironment.DocbookMan = DocbookMan
        SConsEnvironment.DocbookSlidesPdf = DocbookSlidesPdf
        SConsEnvironment.DocbookSlidesHtml = DocbookSlidesHtml
        SConsEnvironment.DocbookXInclude = DocbookXInclude
        SConsEnvironment.DocbookXslt = DocbookXslt


def exists(env):
    return 1