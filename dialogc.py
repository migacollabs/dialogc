import os
import re
import json
import sys
import yaml
import traceback
from optparse import OptionParser
from new import classobj
from keyword import iskeyword
from operator import itemgetter as _itemgetter
from textwrap import dedent
from collections import OrderedDict, Counter
from mako.template import Template
import pprint

__here__ = os.path.abspath(os.path.dirname(__file__))


LogicalModelFlags = ['refl', 'expr', 'cntx', 'trck', 'dynamic', 'static', 'snippet', 'log', 'spoken']

ProtectedNodeNames = ['DOCUMENT']


class DinjLoader(yaml.Loader):

    def __init__(self, stream):
        self._root = os.path.split(stream.name)[0]
        super(DinjLoader, self).__init__(stream)

    def include(self, node):
        filename = os.path.join(self._root, self.construct_scalar(node))
        with open(filename.strip().strip('\n-').strip('\n'), 'r') as f:
            return yaml.load(f, DinjLoader)

DinjLoader.add_constructor('!include', DinjLoader.include)
            
            
class Container(object):
    """ an object that dynamically collects and sets attribute
        from a class definition and keywords on __init__.
        
        future: supporting exclusion of attributes passed based on name
    """
    
    def __init__(self, klass, **kwds):
        klz = self.__class__.__bases__[0] \
            if klass == None \
            else klass
        self._index = {}
        self._set_inners(klz, **kwds)
        self.collect()
    
    def collect(self, excludes=None):
        self._index = \
            [k for k in self.__dict__.keys() 
                if k not in excludes and not k.startswith('_')] \
            if excludes != None \
            else [k for k in self.__dict__.keys() if not k.startswith('_')]
    
    def __getitem__(self, key):
        if type(key)==int:
            if key in self._index:
                return self._index[key], self.__dict__[self._index[key]]
        if key in self.__dict__:
            return self.__dict__[key] 
    
    def __setitem__(self, key, value): 
        self.__dict__[key] = value 
    
    def __delitem__(self, key):
        if key in self.__dict__:
            del self.__dict__[key]
    
    def __contains__(self, key):
        return key in self.__dict__
    
    def _set_inners(self, klass, **kwds):
        try:
            for k,v in kwds.items():
                if type(v) == dict:
                    setattr(self, k, klass(**v))
                else:
                    setattr(self, k,v)
        except:
            print traceback.format_exc()
            
            
def get_lexical_tokens(parsable=None, fromStr=None):
    """ """
    #d = yaml.load(fromStr if fromStr else open(parsable))
    d = yaml.load(fromStr if fromStr else open(parsable), DinjLoader)
    objs = {}
    d2 = {}
    for k,v in d.items():
        if k.startswith('('):
            k, flags = parse_lgcl_mdl_rl_name(k)
            if flags:
                v['__rl_flags__'] = flags
        d2[k] = v
    for k,v in d2.items():
        oClz = classobj('%s'%k,(LexicalToken,), {})
        obj = oClz(parsable, **d2[k])
        objs[oClz.__name__]=obj
    return LexicalToken(parsable, **objs)


def parse_lgcl_mdl_rl_name(s):
    def clean_flag(flag):
        return (flag.strip()
                    .replace(',', '')
                    .replace(';', '')
                    .replace(':', ''))
                    
    if not s.replace(' ', '').endswith(')'):
        raise SyntaxError('This is not a Rule, expecting "):" ending. %s'%s)
        
    s = s.strip()[1:-1].strip()
    elems = [e.strip() for e in s.split(' ') if e]
    if len(elems) >= 1:
        flags = [clean_flag(flag) for flag in elems[1:]]
        flags = [flag for flag in flags if flag in LogicalModelFlags]
        return elems[0], tuple(flags)
    else:
        return elems[0], None
                    

class LexicalToken(Container):
    """
    """
    def __init__(self, parsable=None, **kwds):
        Container.__init__(self, self.__class__, **kwds)
        self.__parsable = parsable

    def items(self, lxtn=None):
        """
            returns .items() 
        """ 
        lxtn = self if lxtn == None else lxtn
        return \
            dict(
                [(k,v,) for k,v in lxtn.__dict__.items() if k in self._index]
            ).items()

    def keys(self, lxtn=None):
        """
            returns .items() 
        """ 
        lxtn = self if lxtn == None else lxtn
        return [k for k in lxtn.__dict__.keys() if k in self._index]

    def find(self, key, lxtn=None, only_lexical_tokens=True):
        raise NotImplemented

    def find_like(self, key, 
                        found=None, lxtn=None, 
                        only_lexical_tokens=True, 
                        eval_obj_name='startswith'):
        raise NotImplemented

    def load(self, **kwds):
        """
        """
        self.__load()
        for k,v in kwds.items():
            setattr(self, k, v)


    def __load(self):

        if self.__parsable:
            self._lex = get_lexical_tokens(self.__parsable)
            for k,v in self._lex.__dict__.items():
                if type(k)==str and not k.startswith('_'):
                    setattr(self, k, v)

    def __getstate__(self):
        """
            remove refecences to dinj anonymous classes
            returns dict of parsable: self.parsable

        """
        return {'__parsable':self.__parsable}
    
    def __setstate__(self, dict):
        """
            reloads inner dinj anonymous classes
        """
        self.__dict__['__parsable'] = dict['__parsable']
        if self.__dict__['__parsable'] != None:
            self.load()


class Lexicon(Container):
    """ """
    def __init__(self, parsable=None, **kwds):
        Container.__init__(self, self.__class__, **kwds)
        if parsable:
            self._lex = get_lexical_tokens(parsable)
            for k,v in self._lex.__dict__.items():
                if type(k)==str and not k.startswith('_'):
                    setattr(self, k, v)
            setattr(self, '__parsable', parsable)

    def items(self):
        return self._lex.items() if self._lex else {}
        

def get_dynamic_static(lex):
    dynamic_c = OrderedDict()
    static_c = OrderedDict()
    for n, c in lex.items():
        if n not in ProtectedNodeNames:
            if '__rl_flags__' in c.__dict__:
                if 'dynamic' in c.__dict__['__rl_flags__']:
                    dynamic_c[n] = c
                elif 'static' in c.__dict__['__rl_flags__']:
                    no = False
                    for flg in ['log', 'snippet', 'spoken']:
                        if flg in c.__dict__['__rl_flags__']:
                            no = True
                    if not no:
                        static_c[n] = c
    print dynamic_c, static_c
    return dynamic_c, static_c


def get_logs(lex):
    log_c = OrderedDict()
    for n, c in lex.items():
        if n not in ProtectedNodeNames:
            if '__rl_flags__' in c.__dict__:
                if 'log' in c.__dict__['__rl_flags__']:
                    log_c[n] = c
    return log_c


def get_snippets(lex):
    snippet_c = OrderedDict()
    for n, c in lex.items():
        if n not in ProtectedNodeNames:
            if '__rl_flags__' in c.__dict__:
                if 'snippet' in c.__dict__['__rl_flags__']:
                    snippet_c[n] = c
    return snippet_c


def get_spoken(lex):
    log_c = OrderedDict()
    for n, c in lex.items():
        if n not in ProtectedNodeNames:
            if '__rl_flags__' in c.__dict__:
                if 'spoken' in c.__dict__['__rl_flags__']:
                    log_c[n] = c
    return log_c


class SpokenBlock(object):
    def __init__(self, char_name, location, description, entries, group_scene=False):
        self.char_name = char_name
        self.location = location
        self.description = description
        self.entries = entries
        self._group_scene = group_scene

    @property
    def IsGroupScene(self):
        return self._group_scene

    @property
    def WordCount(self):
        c = Counter()
        for e in self.entries:
            c.update(e['dialog'].split())
        x = 0
        for v in c.values():
            x += v
        return x


def doit():

    lex = Lexicon(parsable=os.path.abspath(options.DIALOGFILE))
    
    dyn, stc = get_dynamic_static(lex)

    log_entries = get_logs(lex)

    snippets = get_snippets(lex)

    story = {}


    if options.INCLUDEMAIN:
        for cn, c in stc.items():
            if c != None:
                print 'C ->', c
                v = [a.lower() for a in re.split(r'([A-Z][a-z]*)', cn) if a]
                elem_name = '_'.join(v)
                story[elem_name] = c['story_line']
        
    if options.INCLUDEDYN:
        story['dynamic_storyline'] = []
        for cn, c in dyn.items():
            v = [a.lower() for a in re.split(r'([A-Z][a-z]*)', cn) if a]
            elem_name = '_'.join(v)
            for k in c['keyed_storylines'].keys():
                dsl = c['keyed_storylines'][k].__dict__
                c_dsl = dict(dsl)
                for x in c_dsl:
                    if x.startswith('_'):
                        del dsl[x]

                dsl['player_data_key'] = k
                story['dynamic_storyline'].append(dsl)
            

    if options.INCLUDEAUX:
        for cn, c in log_entries.items():
            v = [a.lower() for a in re.split(r'([A-Z][a-z]*)', cn) if a]
            elem_name = '_'.join(v)
            story[elem_name] = c['entries']

        for cn, c in snippets.items():
            v = [a.lower() for a in re.split(r'([A-Z][a-z]*)', cn) if a]
            elem_name = '_'.join(v)
            story[elem_name] = c['snippets']

    djson = json.dumps(story)

    if options.VERBOSE:
        pprint.pprint(story)
    
    with open(os.path.abspath(options.OUTPUTFILE), 'w') as of:
        #of.write(djson)
        pprint.pprint(story, of)

    if options.SCRIPTOUTPUTFILE:

        audio_parts = []
        spoken_entries = get_spoken(lex)

        spoken_x_character = {}
        story_block_x_location = OrderedDict()
        word_count_x_character = {}

        for s in spoken_entries:

            char_name = re.split(r'([A-Z][a-z]*)', s)[1]
            spoken_x_character.setdefault(char_name, [])

            sb = SpokenBlock(char_name, spoken_entries[s].location, spoken_entries[s].description, spoken_entries[s].entries)
            spoken_x_character[char_name].append(sb)
            story_block_x_location.setdefault(sb.location, []).append(sb)

            word_count_x_character.setdefault(char_name, 0)
            word_count_x_character[char_name] += sb.WordCount

        if options.VERBOSE:
            pprint.pprint(word_count_x_character)

        fp = os.path.join(__here__, './scriptlayout.mako')
        fp_t = Template(filename=fp)
        tmpl_vars = dict(
            title=lex.DOCUMENT.title,
            title_description=lex.DOCUMENT.title_description,
            spoken_x_character=spoken_x_character,
            story_block_x_location=story_block_x_location,
            word_count_x_character=word_count_x_character,
            copyright=lex.DOCUMENT.copyright,
            print_footer=True if options.PRINTFOOTER else False
            )
        with open(os.path.join(__here__, os.path.basename(options.SCRIPTOUTPUTFILE)), 'w') as f:
            f.write(fp_t.render(**tmpl_vars))

        
    return True
    
    
def parseArgs(args=None):

    parser = OptionParser()

    parser.add_option("-d", dest="DIALOGFILE", help="Dialog file")
    parser.add_option("-o", dest="OUTPUTFILE", help="Output file")
    parser.add_option("-s", dest="SCRIPTOUTPUTFILE", help="Script Output file")
    parser.add_option("-v", action="store_true", default=False, dest="VERBOSE", help="Verbose")
    parser.add_option("--print-footer", action="store_true", default=False, dest="PRINTFOOTER", help="Print Footer")

    parser.add_option("--include-main", action="store_true", default=False, dest="INCLUDEMAIN", help="Include main conversation")
    parser.add_option("--include-dyn", action="store_true", default=False, dest="INCLUDEDYN", help="Include all dynamic conversations")
    parser.add_option("--include-aux", action="store_true", default=False, dest="INCLUDEAUX", help="Include all auxilary, supporting text")


    (options, args) = parser.parse_args()
    
    if options != None: 
        return options
        
        
if __name__ == '__main__':
    print 'starting dialogc'
    options = parseArgs()
    r = doit()
    
    
    print 'done'

   
    
    
    
    