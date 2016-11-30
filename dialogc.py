import os
import re
import json
import sys
import yaml
import time
import copy
import traceback
try:
	import pyttsx
except:
	pass
import subprocess
import urllib
import shutil
import suds # for cereproc
from optparse import OptionParser
from new import classobj
from keyword import iskeyword
from operator import itemgetter as _itemgetter
from textwrap import dedent
from collections import OrderedDict, Counter
from mako.template import Template
import pprint

from googleapiclient.discovery import build

__here__ = os.path.abspath(os.path.dirname(__file__))


LogicalModelFlags = ['refl', 'expr', 'cntx', 'trck', 'dynamic', 'static', 
						'snippet', 'log', 'spoken', 'robotic', 'localize', 
						'record', 'statement', 'option', 'character']

ProtectedNodeNames = ['DOCUMENT']

EMBEDDED_TRIGGERS = ['VIDEO_INSTANT_PLAY', 'DOSSIER', 'TRIGGER_ACTIVATE', 'CAMERA_TRANSFORM', 'UNLOCK_PLAYER_DATA_KEY']

TRANSLATED_HTML_ESCAPES = {'&#39;': "'"}

voice_engine = None
try:
	voice_engine = pyttsx.init()
	print 'Instantiated voice_engine', pyttsx
except:
	pass


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

	def is_(self, type_name):
		if '__rl_flags__' in self.__dict__:
			if type_name in self.__dict__['__rl_flags__']:
				return True
		return False

	
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
	_prev_names = []
	for n, c in lex.items():
		if n not in ProtectedNodeNames:
			if '__rl_flags__' in c.__dict__:
				if n in _prev_names:
					print '! Non-unique block names. Exiting...'
					sys.exit()
				_prev_names.append(n)
				if 'dynamic' in c.__dict__['__rl_flags__']:
					dynamic_c[n] = c
				elif 'static' in c.__dict__['__rl_flags__']:
					no = False
					for flg in ['log', 'snippet', 'spoken']:
						if flg in c.__dict__['__rl_flags__']:
							no = True
					if not no:
						if not only_blocks or n in only_blocks: 
							static_c[n] = c
							print '.QUEUEING', n

	return dynamic_c, static_c


def get_logs(lex):
	log_c = OrderedDict()
	for n, c in lex.items():
		if n not in ProtectedNodeNames:
			if '__rl_flags__' in c.__dict__:
				if 'log' in c.__dict__['__rl_flags__']:
					if not only_blocks or n in only_blocks: 
						log_c[n] = c
						print '.QUEUEING', n
	return log_c


def get_snippets(lex):
	snippet_c = OrderedDict()
	for n, c in lex.items():
		if n not in ProtectedNodeNames:
			if '__rl_flags__' in c.__dict__:
				if 'snippet' in c.__dict__['__rl_flags__']:
					if not only_blocks or n in only_blocks: 
						snippet_c[n] = c
						print '.QUEUEING', n
	return snippet_c


def get_spoken(lex):
	log_c = OrderedDict()
	for n, c in lex.items():
		if n not in ProtectedNodeNames:
			if '__rl_flags__' in c.__dict__:
				if 'spoken' in c.__dict__['__rl_flags__']:
					if not only_blocks or n in only_blocks:
						log_c[n] = c
						print '.QUEUEING', n
	return log_c


def get_robotic(lex):
	log_c = OrderedDict()
	for n, c in lex.items():
		if n not in ProtectedNodeNames:
			if '__rl_flags__' in c.__dict__:
				if 'robotic' in c.__dict__['__rl_flags__']:
					if not only_blocks or n in only_blocks: 
						log_c[n] = c
						print '.QUEUEING', n
	return log_c


def get_localize(lex):
	log_c = OrderedDict()
	for n, c in lex.items():
		print 'N ->', n
		if n not in ProtectedNodeNames:
			if '__rl_flags__' in c.__dict__:
				if 'localize' in c.__dict__['__rl_flags__']:
					if not only_blocks or n in only_blocks:
						log_c[n] = c
						print '.QUEUEING', n
	return log_c


def clean_embedded_triggers(d, et):
	print '. CLEAN', d, '------', et
	spl = d.split(et)
	parand_tag = spl[1][spl[1].index('('): spl[1].index(')') + 1]
	t = spl[0] + et + parand_tag

	if len(spl) > 1:
		t += spl[1].split(parand_tag)[1]
		
	return t


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

	# pprint.pprint(dyn)

	log_entries = get_logs(lex)

	snippets = get_snippets(lex)

	story = {}

	if options.INCLUDEMAIN:
		for cn, c in stc.items():
			if c != None:
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


	# pprint.pprint(story['dynamic_storyline'])
	# sys.exit()
			

	if options.INCLUDEAUX:
		for cn, c in log_entries.items():
			v = [a.lower() for a in re.split(r'([A-Z][a-z]*)', cn) if a]
			elem_name = '_'.join(v)
			story[elem_name] = c['entries']

		for cn, c in snippets.items():
			v = [a.lower() for a in re.split(r'([A-Z][a-z]*)', cn) if a]
			elem_name = '_'.join(v)
			story[elem_name] = c['snippets']


	if options.INCLUDEVOX:

		global translate_codes, translate_service

		# translate_codes = []
		# translate_service = None
		# if options.TRANSLATE:
		#     translate_service = build('translate', 'v2', developerKey=options.GOOGLEAPIKEY)
		#     for lang_code in options.TRANSLATE.lstrip('[').strip(']').split(','):
		#         translate_codes.append(lang_code.strip().lstrip())


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

		vox_d = {}
		for cn in spoken_x_character.keys():
			char_d = {}
			for loc, sbs in story_block_x_location.items():
				for sb in sbs:
					if sb.char_name == cn:
						char_d.setdefault(loc, {})
						dialog_entries = [e for e in sb.entries]
						char_d[loc]['en'] = dialog_entries

						for t_lang_code in translate_codes:

							print '+ TRANSLATE', t_lang_code, sb.char_name, loc

							attempts = 0
							while attempts < 10:
								try:

									t_res = translate_service.translations().list(
										source='en',
										target=t_lang_code,
										q=[e['dialog'] for e in sb.entries]
									).execute()

									audio_filename = dialog_entries[0]['audio'] if 'audio' in dialog_entries[0] else None
									if audio_filename:
										audio_filename = os.path.splitext(audio_filename)[0]

									translated = []
									for i in range(0, len(dialog_entries)):
										translated.append(
											dict(
												dialog=t_res['translations'][i]['translatedText'],
												audio=audio_filename
												)
											)

									char_d[loc][t_lang_code] = translated

									attempts = 10 # though break should take care of this
									time.sleep(.5)
									break

								except:
									print traceback.format_exc()
									
									time.sleep(1)
									attempts += 1

			vox_d.setdefault(cn, char_d)

		story['character_dialog'] = vox_d


		if options.VERBOSE:
			pprint.pprint(story)


		if translate_codes and translate_service:
			# translated, create lang files

			if 'en' not in translate_codes:
				translate_codes.append('en')

			for t_lang_code in translate_codes:

				t_lang_result = {'character_dialog': {}}

				# {"character_dialog": {"Nasr": {"INT Quadrant 7 - Suspended Animation Sleep Chamber": {"fr": [{"txt":

				for character_name, cd in story['character_dialog'].items():

					t_lang_result['character_dialog'].setdefault(character_name, {})

					for location, langs in cd.items():

						t_lang_result['character_dialog'][character_name].setdefault(location, {})
						t_lang_result['character_dialog'][character_name][location][t_lang_code] = langs[t_lang_code]

				t_json_data = json.dumps(t_lang_result)

				if not options.FLIGHTTEST:
					try:
						with open(t_lang_code + '_subtitles_localized.json', 'w') as of:
							of.write(t_json_data)
					except:
						pass


		# dump the master
		djson = json.dumps(story)

		if not options.FLIGHTTEST:
			try:
				with open('master_subtitles_localized.json', 'w') as of:
					of.write(djson)
			except:
				pass


	# -------------- 


	regen_blocks = []
	if options.REGENBLOCKS:
		for x in options.REGENBLOCKS.lstrip('[').strip(']').split(','):
			regen_blocks.append(x.strip().lstrip())


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
		if not options.FLIGHTTEST:
			with open(os.path.join(__here__, os.path.basename(options.SCRIPTOUTPUTFILE)), 'w') as f:
				f.write(fp_t.render(**tmpl_vars))

		if options.OUTPUTXCHAR:
			try:
				filename, ext = os.path.splitext(options.SCRIPTOUTPUTFILE)

				print spoken_x_character.keys()

				for cn in spoken_x_character.keys():
					char_d = OrderedDict()
					for loc, sbs in story_block_x_location.items():
						for sb in sbs:
							if sb.char_name == cn:
								char_d.setdefault(loc, []).append(sb)

					char_filename = '%s.%s%s'%(filename, cn, ext)
					nfp = os.path.join(__here__, char_filename)

					if char_d:
						fp = os.path.join(__here__, './scriptlayout.mako')
						fp_t = Template(filename=fp)
						tmpl_vars = dict(
							title=lex.DOCUMENT.title,
							title_description=lex.DOCUMENT.title_description,
							spoken_x_character=spoken_x_character,
							story_block_x_location=char_d,
							word_count_x_character={cn:word_count_x_character[cn]},
							copyright=lex.DOCUMENT.copyright,
							print_footer=True if options.PRINTFOOTER else False
							)
						if not options.FLIGHTTEST:
							with open(os.path.join(__here__, char_filename), 'w') as f:
								f.write(fp_t.render(**tmpl_vars))
			except:
				print traceback.format_exc()

	
	if options.ROBOTVOICEGEN:

		# translate_codes = []
		# translate_service = None
		# if options.TRANSLATE:
		#     translate_service = build('translate', 'v2', developerKey=options.GOOGLEAPIKEY)
		#     for lang_code in options.TRANSLATE.lstrip('[').strip(']').split(','):
		#         translate_codes.append(lang_code.strip().lstrip())

		only_pdks = []
		if options.ONLYPDKS:
			for pdk in options.ONLYPDKS.lstrip('[').strip(']').split(','):
				only_pdks.append(pdk.strip().lstrip())

		cereproc_engine = None
		if options.CEREPROCAPIKEY:
			from suds.client import Client
			cereproc_engine = Client("https://cerevoice.com/soap/soap_1_1.php?WSDL")

		robot_dialog = get_robotic(lex)

		result = {}
		master_json = {}
		# master_fp = os.path.join(__here__, 'master_robotspeech.json')
		# master_pfp = os.path.join(__here__, 'master_robotspeech.json.bk')
		master_fp = 'master_robotspeech.json'
		master_pfp = 'master_robotspeech.json.bk'
		if os.path.exists(master_fp):
			try:
				if not options.FLIGHTTEST:
					shutil.copy(master_fp, master_pfp)
			except:
				print 'Can Not SHUTIL Copy', master_fp, '->', master_pfp
				print traceback.format_exc()
			with open(master_fp, 'r') as f:
				try:
					master_data = f.read()
					if master_data:
						master_json = json.loads(master_data)
						print 'Loaded Master JSON', master_json.keys()
				except:
					pass


		for robot_name, rd in robot_dialog.items():

			generated_audio_paths = []

			robot_dir =  os.path.join(__here__, robot_name)
			try:
				os.makedirs(robot_dir)
			except:
				pass


			if robot_name in ignore_blocks:
				print '. IGNORE', robot_name
				try:
					result[robot_name] = master_json[robot_name]
				except:
					pass
				continue


			if hasattr(rd, 'question_answer'):

				for x, t in rd.question_answer.items():

					for lang_code, txt in t.question_text.items():

						#if not lang_code.endswith('_tts'):
						if lang_code == 'en':

							do_translate = True
							do_audio = True

							a_txt = t.answer_text[lang_code]

							result.setdefault(robot_name, {}).setdefault('question_answer', {}).setdefault(x, {}).setdefault(lang_code, {})['answer_text'] = a_txt

							# result.setdefault(robot_name, {}).setdefault(x, {}).setdefault(lang_code, {})['answer_text'] = a_txt

							result[robot_name]['question_answer'][x]['rank'] = t.rank

							q_txt = t.question_text[lang_code]

							result[robot_name]['question_answer'][x][lang_code]['question_text'] = q_txt

							try:
								if master_json[robot_name]['question_answer'][x][lang_code]['question_text'] == q_txt:
									do_translate = False
									do_audio = False
							except:
								pass

							try:
								# check for all requested lang codes
								for t_lang_code in translate_codes:
									_ = master_json[robot_name]['question_answer'][x][t_lang_code]['question_text']
									_ = master_json[robot_name]['question_answer'][x][t_lang_code]['answer_text']
								do_translate = False
								print '. ALL TRANSLATION CODES EXIST IN MASTER. NO TRANSLATION REQ.', str(translate_codes)
							except:
								print traceback.format_exc()
								do_translate = True

							if do_translate:

								print '+ TRANSLATE', x

								if a_txt != None and q_txt != None:

									# translate if needed
									if translate_service and lang_code == 'en':

										for t_lang_code in translate_codes:

											attempts = 0
											while attempts < 10:
												try:

													t_res = translate_service.translations().list(
														source='en',
														target=t_lang_code,
														q=[q_txt, a_txt]
													).execute()

													t_q_txt = t_res['translations'][0]['translatedText']
													t_a_txt = t_res['translations'][1]['translatedText']

													for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
														t_q_txt = t_q_txt.replace(k_, v_)
														t_a_txt = t_a_txt.replace(k_, v_)

													result[robot_name]['question_answer'][x].setdefault(t_lang_code, {})['question_text'] = t_q_txt
													result[robot_name]['question_answer'][x][t_lang_code]['answer_text'] = t_a_txt

													attempts = 10 # though break should take care of this
													time.sleep(.15)
													break

												except:
													print traceback.format_exc()
													
													attempts += 1
													time.sleep(1*attempts)

								else:
									for t_lang_code in translate_codes:
										result[robot_name]['question_answer'][x].setdefault(t_lang_code, {})
										result[robot_name]['question_answer'][x][t_lang_code]['question_text'] = None
										result[robot_name]['question_answer'][x][t_lang_code]['answer_text'] = None

							else:

								print '. TRANSLATE', x

								try:
									for t_lang_code in translate_codes:
										result[robot_name]['question_answer'][x].setdefault(t_lang_code, {})
										result[robot_name]['question_answer'][x][t_lang_code]['question_text'] = master_json[robot_name]['question_answer'][x][t_lang_code]['question_text']
										result[robot_name]['question_answer'][x][t_lang_code]['answer_text'] = master_json[robot_name]['question_answer'][x][t_lang_code]['answer_text']
								except:
									print traceback.format_exc()


							if not options.ONLYENROBOTVOICEGEN or (options.ONLYENROBOTVOICEGEN and lang_code == 'en'):

								wav_file = None

								if not 'use_ext_audio' in t or t['use_ext_audio'] == False:

									process_audio = False

									# check to see if text has changed
									try:
										if master_json[robot_name]['question_answer'][x]['en']['answer_text'] != t.answer_text[lang_code]:
											process_audio = True
									except:
										print traceback.format_exc()
										process_audio = True


									# override if this block is flagged
									if regen_blocks:
										if robot_name in regen_blocks or 'ALL' in regen_blocks:
											process_audio = True

									wav_file = os.path.join(robot_dir, x + '.wav')
									if lang_code != 'en' and not options.ONLYENROBOTVOICEGEN:
										wav_file = os.path.join(robot_dir, lang_code + '_' + x + '.wav')

									generated_audio_paths.append(wav_file)

									result[robot_name]['question_answer'][x][lang_code]['audio'] = os.path.splitext(os.path.basename(wav_file))[0]

									try:
										if master_json[robot_name]['question_answer'][x][lang_code]['audio'] == result[robot_name]['question_answer'][x][lang_code]['audio']:
											process_audio = do_audio
									except:
										process_audio = True


									v_txt = t.answer_text[lang_code]
									if 'en_tts' in t.answer_text:
										v_txt = t.answer_text['en_tts']
										result[robot_name]['question_answer'][x].setdefault('pronuctiation', {})['answer_text'] = v_txt

										try:
											if master_json[robot_name]['question_answer'][x]['pronuctiation']['answer_text'] != v_txt:
												process_audio = True
										except:
											process_audio = True


									if process_audio:

										print '+ AUDIO', x

										if rd.tts == 'nsss' and (not only_pdks or (only_pdks and x in only_pdks)):

											try:
												voice_engine.setProperty('voice', rd.voice)
												voice_engine.speakToFile(v_txt, wav_file)
												voice_engine.runAndWait()
											except:
												print traceback.format_exc()

										elif rd.tts == 'festival' and (not only_pdks or (only_pdks and x in only_pdks)):

											pass

											# echo "This is a test" | ./text2wave -o output.wav -eval "(voice_rab_diphone)"

											cmd = 'echo ' + '"' + v_txt +  '"' + ' | text2wave -o ' + wav_file + ' -eval "(%s)"'%rd.voice

											try:
												subprocess.call(cmd, shell=True)
											except:
												print traceback.format_exc()

										# OR USE THE CERE PROC CLOUD
										elif rd.tts == 'cereproc' and cereproc_engine and (not only_pdks or (only_pdks and x in only_pdks)):

											request = cereproc_engine.service.speakSimple(
												options.CEREPROCAPIKEY, 
												options.CEREPROCAPIPSSWRD, rd.voice, v_txt)
											if request.resultCode == 1:
												audio_file = urllib.URLopener()
												audio_file.retrieve(request.fileUrl, wav_file+'.ogg')


											print '. DOWNLOADED', os.stat(wav_file+'.ogg').st_size, wav_file+'.ogg'


											output_filename = None

											if options.OGGTOWAV:

												if os.path.exists(wav_file+'.ogg'):

													# convert to wav

													output_filename = wav_file

													convert_cmd = 'ffmpeg -y -i "%s" "%s"'%(wav_file+'.ogg', wav_file)

													print '. PROCESSING OGGTOWAV CMD', convert_cmd

													try:
														subprocess.call(convert_cmd, shell=True)

														os.remove(wav_file+'.ogg')

													except:
														print traceback.format_exc()
												else:
													print 'Expected OGG output file %s from Cereproc Engine'%wav_file+'.ogg'

											elif options.WAVTOOGG:

												if os.path.exists(wav_file):

													# convert to wav
													# ffmpeg -i audio.wav  -acodec libvorbis audio.ogg

													output_filename = wav_file+'.ogg'

													convert_cmd = 'ffmpeg -y -i "%s" -acodec libvorbis "%s"'%(wav_file, output_filename)

													print '. PROCESSING FFMEG CMD WAVTOOGG', convert_cmd

													try:
														subprocess.call(convert_cmd, shell=True)

														os.remove(wav_file+'.ogg')

													except:
														print traceback.format_exc()


											print '. CHECKING POST PROCESSING', hasattr(rd, 'post_processing')
											
											# process wav if necessary
											# move to Resources/Audio/Dialog/{robot_name_dir}
											try:

												if output_filename.endswith('.wav'):
													# only post process wavs

													if hasattr(rd, 'post_processing'):
														# there is a post process command

														print '. DOING POST PROCESSING'

														for pp in rd.post_processing:

															post_process_cmd = pp.replace('${INPUTFILE}', wav_file).replace('${OUTPUTFILE}', output_filename)

															# inset 'win' into cmd
															# crunchy.sh becomes crunchywin.sh
															if sys.platform == 'win32':
																elems = post_process_cmd.split('.sh')
																elems.insert(1, 'win.sh')
																post_process_cmd = ''.join(elems)

															print '. POST PROCESSING CMD', post_process_cmd

															ret_code = subprocess.call(post_process_cmd, shell=True)

															print '. POST_PROCESSING', ret_code

															# convert back to ogg for unity

															input_filename = output_filename + '.wav' # add extra ext that was added by .sh

															print '. FILESIZE FOR PROCESSING', os.stat(input_filename).st_size, input_filename

															output_filename = os.path.splitext(wav_file)[0] +'.ogg'

															convert_cmd = 'ffmpeg -y -i "%s" -acodec libvorbis "%s"'%(input_filename, output_filename)

															print '. PROCESSING FFMEG CMD', convert_cmd

															try:
																subprocess.call(convert_cmd, shell=True)

																# move file to resources
																	
																audio_resource_robot_audio_dir = \
																	os.path.join('../Assets/Resources/Audio/Dialogue', robot_name)

																try:
																	os.makedirs(audio_resource_robot_audio_dir)
																except:
																	pass

																audio_resource_robot_audio_file = os.path.join(audio_resource_robot_audio_dir, os.path.basename(output_filename))

																shutil.copy(output_filename, audio_resource_robot_audio_file)

																new_filesz = os.stat(audio_resource_robot_audio_file).st_size

																print '. COPIED', new_filesz, audio_resource_robot_audio_file

																os.remove(input_filename)
																os.remove(output_filename)

															except:
																print traceback.format_exc()

											except:
												print traceback.format_exc()

									else:

										print '. AUDIO', x

								else:
									result[robot_name]['question_answer'][x][lang_code]['audio'] = wav_file
									result[robot_name]['question_answer'][x][lang_code]['use_ext_audio'] = True

									
			if hasattr(rd, 'greetings') and rd.greetings != None:

				do_translate_flags = {}
				try:
					g_pos = 0
					for greeting in rd.greetings:
						if greeting:
							for k, v in greeting.items():
								if 'greetings' not in regen_block_categories:

									# force translation because its broken
									# do_translate_flags[k] = True

									try:
										if master_json[robot_name]['greetings']['en'][g_pos]['txt'] != v['en'] or master_json[robot_name]['greetings']['en'][g_pos]['key'] != k:
											do_translate_flags[k] = True

										else:
											print ". CHECK PRONUCTIATION -", k
											# alse check en_tts pronuctiation options
											if 'en_tts' in v:
												if master_json[robot_name]['greetings']['en'][g_pos]['en_tts'] != v['en_tts']:
													do_translate_flags[k] = True

											else:
												if 'en_tts' in master_json[robot_name]['greetings']['en'][g_pos] and master_json[robot_name]['greetings']['en'][g_pos]['en_tts'] != None:
													# it was removed
													do_translate_flags[k] = True


											print ". CHECK LANGUAGUES -", k   
											# check for all languages
											for t_lang_code in translate_codes:
												if t_lang_code not in master_json[robot_name]['greetings'] or not master_json[robot_name]['greetings'][t_lang_code]:
													do_translate_flags[k] = True
													break
									except:
										do_translate_flags[k] = True

								else:

									print '. OVERRIDE REGENERATE', k
									do_translate_flags[k] = True

								g_pos += 1

				except:
					print traceback.format_exc()


				for greeting in rd.greetings:
					if greeting:
						for k, v in greeting.items():

							txt = v['en']
							en_tts = v['en_tts'] if 'en_tts' in v else None

							wav_file = os.path.join(robot_dir,  robot_name + '_' + k + '.wav')
							audio_for_txt = os.path.splitext(os.path.basename(wav_file))[0]

							result.setdefault(robot_name, {}).setdefault('greetings', {}).setdefault('en', []).append(
								{
									'key':k,
									'txt':txt,
									'en_tts':en_tts,
									'audio':os.path.splitext(os.path.basename(wav_file))[0],
									'use_ext_audio':v['use_ext_audio'] if 'use_ext_audio' in v else None
								}
							)

							if k in do_translate_flags:

								print '+ TRANSLATE GREETING', k

								# translate if needed
								if translate_service:

									for t_lang_code in translate_codes:
										attempts = 0
										while attempts < 10:
											try:

												t_res = translate_service.translations().list(
													source='en',
													target=t_lang_code,
													q=[txt]
												).execute()

												t_txt = t_res['translations'][0]['translatedText']
												for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
													t_txt = t_txt.replace(k_, v_)

												result[robot_name]['greetings'].setdefault(t_lang_code, []).append(
													{
														'key':k,
														'txt':t_txt,
														'en_tts':en_tts,
														'audio':audio_for_txt,
														'use_ext_audio':v['use_ext_audio'] if 'use_ext_audio' in v else None
													}
												)

												attempts = 10 # though break should take care of this
												time.sleep(.15)
												break

											except:
												print traceback.format_exc()
												
												attempts += 1
												time.sleep(1*attempts)
								else:

									raise Exception('No translation service enabled')

							else:

								try:
									# print '. LISTING PREVIOUS TRANSLATE'
									# pprint.pprint(result[robot_name]['greetings'])

									for t_lang_code in translate_codes:
										try: 
											result[robot_name]['greetings'][t_lang_code] = master_json[robot_name]['greetings'][t_lang_code]
										except:
											print 'WARNING! Missing lang code from master? ', traceback.format_exc()

								except:
									pass

								#sys.exit()


							wav_file = None
							lang_code = 'en' # force it to en
							if not options.ONLYENROBOTVOICEGEN or (options.ONLYENROBOTVOICEGEN and lang_code == 'en'):

								if not 'use_ext_audio' in v or v['use_ext_audio'] == False:

									process_audio = k in do_translate_flags

									wav_file = os.path.join(robot_dir,  robot_name + '_' + k + '.wav')
									if lang_code != 'en' and not options.ONLYENROBOTVOICEGEN:
										wav_file = os.path.join(robot_dir, robot_name + '_' + lang_code + '_' + k + '.wav')

									generated_audio_paths.append(wav_file)

									result[robot_name]['greetings']['en'][-1:][0]['audio'] = os.path.splitext(os.path.basename(wav_file))[0]

									v_txt = txt
									if 'en_tts' in v:
										v_txt = v['en_tts']


									# TODO: check to see if text has changed


									# override if this block is flagged
									if regen_blocks:
										if robot_name in regen_blocks or 'ALL' in regen_blocks:
											process_audio = True


									if process_audio:

										print '+ AUDIO', k

										if rd.tts == 'nsss' and (not only_pdks or (only_pdks and x in only_pdks)):
											try:
												voice_engine.setProperty('voice', rd.voice)
												voice_engine.speakToFile(v_txt, wav_file)
												voice_engine.runAndWait()
											except:
												print traceback.format_exc()

										elif rd.tts == 'festival' and (not only_pdks or (only_pdks and x in only_pdks)):

											# echo "This is a test" | ./text2wave -o output.wav -eval "(voice_rab_diphone)"

											cmd = 'echo ' + '"' + v_txt +  '"' + ' | text2wave -o ' + wav_file + ' -eval "(%s)"'%rd.voice

											try:
												subprocess.call(cmd, shell=True)
											except:
												print traceback.format_exc()

										# OR USE THE CERE PROC CLOUD
										elif rd.tts == 'cereproc' and cereproc_engine and (not only_pdks or (only_pdks and x in only_pdks)):

											request = cereproc_engine.service.speakSimple(
												options.CEREPROCAPIKEY, 
												options.CEREPROCAPIPSSWRD, rd.voice, v_txt)
											if request.resultCode == 1:
												audio_file = urllib.URLopener()
												audio_file.retrieve(request.fileUrl, wav_file+'.ogg')


											print '. DOWNLOADED', os.stat(wav_file+'.ogg').st_size, wav_file+'.ogg'

											output_filename = wav_file

											if os.path.exists(wav_file+'.ogg'):

												# convert to wav

												convert_cmd = 'ffmpeg -y -i "%s" "%s"'%(wav_file+'.ogg', wav_file)

												try:
													subprocess.call(convert_cmd, shell=True)

													os.remove(wav_file+'.ogg')

												except:
													print traceback.format_exc()

											else:
												print 'Expected OGG output file %s from Cereproc Engine'%wav_file+'.ogg'


										print '. CONVERTED', os.stat(wav_file).st_size, wav_file


										# process wav if necessary
										# move to Resources/Audio/Dialog/{robot_name_dir}
										try:

											if output_filename.endswith('.wav'):
												# only post process wavs

												if hasattr(rd, 'post_processing'):
													# there is a post process command

													for pp in rd.post_processing:

														post_process_cmd = pp.replace('${INPUTFILE}', wav_file).replace('${OUTPUTFILE}', output_filename)

														# inset 'win' into cmd
														# crunchy.sh becomes crunchywin.sh
														if sys.platform == 'win32':
															elems = post_process_cmd.split('.sh')
															elems.insert(1, 'win.sh')
															post_process_cmd = ''.join(elems)

														print '. POST PROCESSSING CMD', post_process_cmd

														ret_code = subprocess.call(post_process_cmd, shell=True)

														print '. POST_PROCESSING', ret_code

														# convert back to ogg for unity

														input_filename = output_filename + '.wav' # add extra ext that was added by .sh

														print '. FILESIZE FOR PROCESSING', os.stat(input_filename).st_size, input_filename

														output_filename = os.path.splitext(wav_file)[0] +'.ogg'

														convert_cmd = 'ffmpeg -y -i "%s" -acodec libvorbis "%s"'%(input_filename, output_filename)

														try:
															subprocess.call(convert_cmd, shell=True)

															# move file to resources
																
															audio_resource_robot_audio_dir = \
																os.path.join('../Assets/Resources/Audio/Dialogue', robot_name)

															try:
																os.makedirs(audio_resource_robot_audio_dir)
															except:
																pass

															audio_resource_robot_audio_file = os.path.join(audio_resource_robot_audio_dir, os.path.basename(output_filename))

															shutil.copy(output_filename, audio_resource_robot_audio_file)

															new_filesz = os.stat(audio_resource_robot_audio_file).st_size

															print '. COPIED', new_filesz, audio_resource_robot_audio_file

															os.remove(input_filename)
															os.remove(output_filename)

														except:
															print traceback.format_exc()

										except:
											print traceback.format_exc()


									else:

										print '. AUDIO FOR GREETING', k

					else:
						break
						# it exists but doesn't need translation

						# result[robot_name]['greetings'] = master_json[robot_name]['greetings']


			# TODO: refactor this into funcs to render wavs, etc..
			
			if hasattr(rd, 'random') and rd.random != None:
				for x, t in rd.random.items():

					for lang_code, txt in t.question_text.items():

						#if not lang_code.endswith('_tts'):
						if lang_code == 'en':

							do_translate = True
							do_audio = False

							a_txt = t.answer_text[lang_code]

							result.setdefault(robot_name, {}).setdefault('random', {}).setdefault(x, {}).setdefault(lang_code, {})['answer_text'] = a_txt

							result[robot_name]['random'][x]['rank'] = t.rank

							q_txt = t.question_text[lang_code]

							result[robot_name]['random'][x][lang_code]['question_text'] = t.question_text[lang_code]

							try:
								if master_json[robot_name]['random'][x][lang_code]['question_text'] == q_txt:
									do_translate = False
							except:
								print traceback.format_exc()
								do_translate = True
								do_audio = True

							try:
								# check for all requested lang codes
								for t_lang_code in translate_codes:
									_ = master_json[robot_name]['random'][x][t_lang_code]['question_text']
									_ = master_json[robot_name]['random'][x][t_lang_code]['answer_text']
								do_translate = False
								print '. ALL TRANSLATION CODES EXIST IN MASTER', str(translate_codes)
							except:
								print traceback.format_exc()
								do_translate = True
								do_audio = True

							if do_translate:

								if a_txt != None and q_txt != None:

									# translate if needed
									if translate_service and lang_code == 'en':

										for t_lang_code in translate_codes:
											attempts = 0
											while attempts < 10:
												try:

													t_res = translate_service.translations().list(
														source='en',
														target=t_lang_code,
														q=[q_txt, a_txt]
													).execute()

													t_q_txt = t_res['translations'][0]['translatedText']
													t_a_txt = t_res['translations'][1]['translatedText']

													for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
														t_q_txt = t_q_txt.replace(k_, v_)
														t_a_txt = t_a_txt.replace(k_, v_)

													result[robot_name]['random'][x].setdefault(t_lang_code, {})['question_text'] = t_q_txt
													result[robot_name]['random'][x][t_lang_code]['answer_text'] = t_a_txt

													attempts = 10 # though break should take care of this
													time.sleep(.15)
													break

												except:
													print traceback.format_exc()
													
													attempts += 1
													time.sleep(1*attempts)

								else:
									try:
										for t_lang_code in translate_codes:
											result[robot_name]['random'][x].setdefault(t_lang_code, {})
											result[robot_name]['random'][x][t_lang_code]['question_text'] = None
											result[robot_name]['random'][x][t_lang_code]['answer_text'] = None
									except:
										print traceback.format_exc()
							else:
								print '. NO TRANSLATION PERFORMED', str(translate_codes)
								try:
									for t_lang_code in translate_codes:
										result[robot_name]['random'][x].setdefault(t_lang_code, {})
										result[robot_name]['random'][x][t_lang_code]['question_text'] = master_json[robot_name]['random'][x][t_lang_code]['question_text']
										result[robot_name]['random'][x][t_lang_code]['answer_text'] = master_json[robot_name]['random'][x][t_lang_code]['answer_text']
								except:
									print traceback.format_exc()


							if not options.ONLYENROBOTVOICEGEN or (options.ONLYENROBOTVOICEGEN and lang_code == 'en'):

								wav_file = None

								if not 'use_ext_audio' in t or t['use_ext_audio'] == False:

									process_audio = True

									wav_file = os.path.join(robot_dir, x + '.wav')
									if lang_code != 'en' and not options.ONLYENROBOTVOICEGEN:
										wav_file = os.path.join(robot_dir, lang_code + '_' + x + '.wav')

									generated_audio_paths.append(wav_file)

									result[robot_name]['random'][x][lang_code]['audio'] = os.path.splitext(os.path.basename(wav_file))[0]

									try:
										if master_json[robot_name]['random'][x][lang_code]['audio'] == result[robot_name]['random'][x][lang_code]['audio']:
											process_audio = do_audio
											print 'CHECK THIS OUT'
											print
											print master_json[robot_name]['random'][x][lang_code]['audio']
											print result[robot_name]['random'][x][lang_code]['audio']
											print 'DO AUDIO ?', do_audio
									except:
										print traceback.format_exc()
										pass

									v_txt = t.answer_text[lang_code]
									if 'en_tts' in t.answer_text:
										v_txt = t.answer_text['en_tts']

										result[robot_name]['random'][x].setdefault('pronuctiation', {})['answer_text'] = v_txt
										
										try:
											if master_json[robot_name]['random'][x]['pronuctiation']['answer_text'] != v_txt:
												process_audio = True
										except:
											print traceback.format_exc()
											process_audio = True

									# check to see if text has changed
									try:
										if master_json[robot_name]['random'][x]['en']['answer_text'] != t.answer_text[lang_code]:
											process_audio = True
									except:
										print traceback.format_exc()
										process_audio = True


									# override if this block is flagged
									if regen_blocks:
										if robot_name in regen_blocks or 'ALL' in regen_blocks:
											process_audio = True


									if process_audio:

										print '+ AUDIO', x

										if rd.tts == 'nsss' and (not only_pdks or (only_pdks and x in only_pdks)):
											try:
												voice_engine.setProperty('voice', rd.voice)
												voice_engine.speakToFile(v_txt, wav_file)
												voice_engine.runAndWait()
											except:
												print traceback.format_exc()

										elif rd.tts == 'festival' and (not only_pdks or (only_pdks and x in only_pdks)):

											# echo "This is a test" | ./text2wave -o output.wav -eval "(voice_rab_diphone)"

											cmd = 'echo ' + '"' + v_txt +  '"' + ' | text2wave -o ' + wav_file + ' -eval "(%s)"'%rd.voice

											try:
												subprocess.call(cmd, shell=True)
											except:
												print traceback.format_exc()

										# OR USE THE CERE PROC CLOUD
										elif rd.tts == 'cereproc' and cereproc_engine and (not only_pdks or (only_pdks and x in only_pdks)):
											
											request = cereproc_engine.service.speakSimple(
												options.CEREPROCAPIKEY, 
												options.CEREPROCAPIPSSWRD, rd.voice, v_txt)
											if request.resultCode == 1:
												audio_file = urllib.URLopener()
												audio_file.retrieve(request.fileUrl, wav_file+'.ogg')

											output_filename = wav_file

											if os.path.exists(wav_file+'.ogg'):

												print '. DOWNLOADED', os.stat(wav_file+'.ogg').st_size, wav_file+'.ogg'

												# convert to wav

												convert_cmd = 'ffmpeg -y -i "%s" "%s"'%(wav_file+'.ogg', wav_file)

												try:
													subprocess.call(convert_cmd, shell=True)

													os.remove(wav_file+'.ogg')

												except:
													print traceback.format_exc()
											else:
												raise Exception('Expected OGG output file %s from Cereproc Engine'%wav_file+'.ogg')


											# process wav if necessary
											# move to Resources/Audio/Dialog/{robot_name_dir}
											try:

												if output_filename.endswith('.wav'):
													# only post process wavs

													if hasattr(rd, 'post_processing'):
														# there is a post process command

														for pp in rd.post_processing:

															# process audio

															post_process_cmd = pp.replace('${INPUTFILE}', wav_file).replace('${OUTPUTFILE}', output_filename)

															# inset 'win' into cmd
															# crunchy.sh becomes crunchywin.sh
															if sys.platform == 'win32':
																elems = post_process_cmd.split('.sh')
																elems.insert(1, 'win.sh')
																post_process_cmd = ''.join(elems)

															print '. POST PROCESSING CMD', post_process_cmd

															ret_code = subprocess.call(post_process_cmd, shell=True)

															print '. POST PROCESSING', ret_code


															# convert back to ogg for unity

															input_filename = output_filename + '.wav' # add extra ext that was added by .sh

															output_filename = os.path.splitext(wav_file)[0] +'.ogg'

															convert_cmd = 'ffmpeg -y -i "%s" -acodec libvorbis "%s"'%(input_filename, output_filename)

															try:
																subprocess.call(convert_cmd, shell=True)
																

																# convert back to ogg for unity

																# input_filename = output_filename

																print '. FILESIZE FOR PROCESSING', os.stat(input_filename).st_size, input_filename

																output_filename = os.path.splitext(wav_file)[0]+'.ogg'

																convert_cmd = 'ffmpeg -y -i "%s" -acodec libvorbis "%s"'%(input_filename, output_filename)

																print '. FFMPEG WAVTOOGG CMD', convert_cmd

																try:
																	subprocess.call(convert_cmd, shell=True)

																	# move file to resources
																		
																	audio_resource_robot_audio_dir = \
																		os.path.join('../Assets/Resources/Audio/Dialogue', robot_name)

																	try:
																		os.makedirs(audio_resource_robot_audio_dir)
																	except:
																		pass

																	audio_resource_robot_audio_file = os.path.join(audio_resource_robot_audio_dir, os.path.basename(output_filename))

																	shutil.copy(output_filename, audio_resource_robot_audio_file)

																	new_filesz = os.stat(audio_resource_robot_audio_file).st_size

																	print '. COPIED', new_filesz, audio_resource_robot_audio_file

																	os.remove(input_filename)
																	# os.remove(output_filename)

																except:
																	print traceback.format_exc()

															except:
																print traceback.format_exc()


											except:
												print traceback.format_exc()
												raise Exception(". ERROR IN PROCESSING")


									else:

										print '. AUDIO', x

								else:
									result[robot_name]['random'][x][lang_code]['audio'] = wav_file
									result[robot_name]['random'][x][lang_code]['use_ext_audio'] = True



			if hasattr(rd, 'statements'):

				print 'Processing statements for ', robot_name

				for x, t in rd.statements.items():

					result.setdefault(robot_name, {}).setdefault('statements', {}).setdefault(x, {})['en'] = t['en']

					do_translate = True
					do_audio = True

					try:
						if master_json[robot_name]['statements'][x]['en'] == result[robot_name]['statements'][x]['en']:
							do_translate = False
							do_audio = False
					except:
						do_translate = True

					try:
						# check for all requested lang codes
						for t_lang_code in translate_codes:
							_ = master_json[robot_name]['statements'][x][t_lang_code]
						do_translate = False
					except:
						do_translate = True

					if do_translate:

						if t['en'] != None:
							# translate if needed
							if translate_service:

								print '+ TRANSLATE', x

								for t_lang_code in translate_codes:
									attempts = 0
									while attempts < 10:
										try:
											t_res = translate_service.translations().list(
												source='en',
												target=t_lang_code,
												q=[t['en']]
											).execute()

											t_txt = t_res['translations'][0]['translatedText']

											for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
												t_txt = t_txt.replace(k_, v_)

											result[robot_name]['statements'][x][t_lang_code] = t_txt

											attempts = 10 # though break should take care of this
											time.sleep(.5)
											break

										except:
											print traceback.format_exc()
											
											attempts += 1
											time.sleep(1*attempts)

						else:
							for t_lang_code in translate_codes:
								result[robot_name]['statements'][x][t_lang_code] = None
					else:

						print '. TRANSLATE', x

						try:
							for t_lang_code in translate_codes:
								result[robot_name]['statements'][x][t_lang_code] = master_json[robot_name]['statements'][x][t_lang_code]
						except:
							pass

					wav_file = None

					if not 'use_ext_audio' in t or t['use_ext_audio'] == False:

						process_audio = do_audio

						wav_file = os.path.join(robot_dir, x + '.wav')

						generated_audio_paths.append(wav_file)
						
						lang_code = 'en' # force this

						if lang_code != 'en' and not options.ONLYENROBOTVOICEGEN:
							wav_file = os.path.join(robot_dir, lang_code + '_' + x + '.wav')

						result[robot_name]['statements'][x]['audio'] = os.path.splitext(os.path.basename(wav_file))[0]

						try:
							if master_json[robot_name]['statements'][x]['audio'] == result[robot_name]['statements'][x]['audio']:
								process_audio = do_translate
						except:
							pass


						v_txt = t['en']
						if 'en_tts' in t:
							v_txt = t['en_tts']

							result[robot_name]['statements'][x].setdefault('pronuctiation', v_txt)
							try:
								if master_json[robot_name]['statements'][x]['pronuctiation'] != v_txt:
									process_audio = True
							except:
								process_audio = True

						# check to see if text has changed
						try:
							if master_json[robot_name]['statements'][x]['en'] != t['en']:
								process_audio = True
						except:
							print traceback.format_exc()


						# override if this block is flagged
						if regen_blocks:
							if robot_name in regen_blocks or 'ALL' in regen_blocks:
								process_audio = True


						if process_audio:

							print '+ AUDIO', x

							if rd.tts == 'nsss' and (not only_pdks or (only_pdks and x in only_pdks)):

								try:
									voice_engine.setProperty('voice', rd.voice)
									voice_engine.speakToFile(v_txt, wav_file)
									voice_engine.runAndWait()
								except:
									print traceback.format_exc()

							elif rd.tts == 'festival' and (not only_pdks or (only_pdks and x in only_pdks)):

								# echo "This is a test" | ./text2wave -o output.wav -eval "(voice_rab_diphone)"

								cmd = 'echo ' + '"' + v_txt +  '"' + ' | text2wave -o ' + wav_file + ' -eval "(%s)"'%rd.voice

								try:
									subprocess.call(cmd, shell=True)
								except:
									print traceback.format_exc()


							# OR USE THE CERE PROC CLOUD
							elif rd.tts == 'cereproc' and cereproc_engine and (not only_pdks or (only_pdks and x in only_pdks)):

								request = cereproc_engine.service.speakSimple(
									options.CEREPROCAPIKEY, 
									options.CEREPROCAPIPSSWRD, rd.voice, v_txt)
								if request.resultCode == 1:
									audio_file = urllib.URLopener()
									audio_file.retrieve(request.fileUrl, wav_file+'.ogg')


								print '. DOWNLOADED', os.stat(wav_file+'.ogg').st_size, wav_file+'.ogg'

								output_filename = wav_file


								if os.path.exists(wav_file+'.ogg'):

									# convert to wav

									convert_cmd = 'ffmpeg -y -i "%s" "%s"'%(wav_file+'.ogg', wav_file)

									try:
										subprocess.call(convert_cmd, shell=True)

										os.remove(wav_file+'.ogg')

									except:
										print traceback.format_exc()

								else:
									print 'Expected OGG output file %s from Cereproc Engine'%wav_file+'.ogg'



								# process wav if necessary
								# move to Resources/Audio/Dialog/{robot_name_dir}
								try:

									if output_filename.endswith('.wav'):
										# only post process wavs

										if hasattr(rd, 'post_processing'):
											# there is a post process command

											for pp in rd.post_processing:

												post_process_cmd = pp.replace('${INPUTFILE}', wav_file).replace('${OUTPUTFILE}', output_filename)

												# inset 'win' into cmd
												# crunchy.sh becomes crunchywin.sh
												if sys.platform == 'win32':
													elems = post_process_cmd.split('.sh')
													elems.insert(1, 'win.sh')
													post_process_cmd = ''.join(elems)

												print '. POST PROCESSING CMD', post_process_cmd

												ret_code = subprocess.call(post_process_cmd, shell=True)

												print '. POST_PROCESSING', ret_code


												# convert back to ogg for unity

												input_filename = output_filename + '.wav' # add extra ext that was added by .sh

												print '. FILESIZE FOR PROCESSING', os.stat(input_filename).st_size, input_filename

												output_filename = os.path.splitext(wav_file)[0] +'.ogg'

												convert_cmd = 'ffmpeg -y -i "%s" -acodec libvorbis "%s"'%(input_filename, output_filename)

												print '. CONVERT CMD', convert_cmd

												try:
													subprocess.call(convert_cmd, shell=True)

													# move file to resources
														
													audio_resource_robot_audio_dir = \
														os.path.join('../Assets/Resources/Audio/Dialogue', robot_name)

													try:
														os.makedirs(audio_resource_robot_audio_dir)
													except:
														pass

													audio_resource_robot_audio_file = os.path.join(audio_resource_robot_audio_dir, os.path.basename(output_filename))

													shutil.copy(output_filename, audio_resource_robot_audio_file)

													new_filesz = os.stat(audio_resource_robot_audio_file).st_size

													print '. COPIED', new_filesz, audio_resource_robot_audio_file

													os.remove(input_filename)
													os.remove(output_filename)

												except:
													print traceback.format_exc()

								except:
									print traceback.format_exc()


						else:
							print '. AUDIO', x

					else:
						result[robot_name]['statements'][x]['audio'] = wav_file
						result[robot_name]['statements'][x]['use_ext_audio'] = True




			# remove audio files that are no longer referenced
			try:
				files = [os.path.join(robot_dir, f) for f in os.listdir(robot_dir) if os.path.isfile(os.path.join(robot_dir, f))]
				for fck in files:
					if fck not in generated_audio_paths:
						try:
							if os.path.exists(fck):
								os.remove(fck)
								print '- AUDIO', fck
						except:
							print 'Error removing unreferenced audio file', traceback.format_exc()
			except:
				print traceback.format_exc()



		if translate_codes and translate_service:
			# translated, create lang files

			print '. TRANSLATION CODES', translate_codes

			if 'en' not in translate_codes:
				translate_codes.append('en')

			for t_lang_code in translate_codes:

				t_lang_result = {}

				for k,v in result.items():
					if 'statements' in v.keys():
						t_lang_result.setdefault(k, {}).setdefault('statements', {})
						for s_k, s_v in v['statements'].items():
							t_lang_result[k].setdefault('statements', {}).setdefault(s_k, {})[t_lang_code] = result[k]['statements'][s_k][t_lang_code]

							try:
								t_lang_result[k]['statements'][s_k]['audio'] = result[k]['statements'][s_k]['audio']
							except:
								print '.... NO AUDIO', k, t_lang_result[k]['statements'][s_k]
					
					if 'random' in v.keys():
						t_lang_result.setdefault(k, {}).setdefault('random', {})
						for s_k, s_v in v['random'].items():
							t_lang_result[k]['random'].setdefault(s_k, {})['question_text'] = result[k]['random'][s_k][t_lang_code]['question_text']
							t_lang_result[k]['random'][s_k]['answer_text'] = result[k]['random'][s_k][t_lang_code]['answer_text']
							t_lang_result[k]['random'][s_k]['rank'] = result[k]['random'][s_k]['rank']

							try:
								t_lang_result[k]['random'][s_k]['audio'] = result[k]['random'][s_k]['en']['audio']
							except:
								print '.... NO AUDIO', k, t_lang_result[k]['random'][s_k]

					if 'question_answer' in v.keys():
						t_lang_result.setdefault(k, {}).setdefault('question_answer', {})
						for s_k, s_v in v['question_answer'].items():

							try: 
								t_lang_result[k]['question_answer'].setdefault(s_k, {})['question_text'] = result[k]['question_answer'][s_k][t_lang_code]['question_text']
								t_lang_result[k]['question_answer'][s_k]['answer_text'] = result[k]['question_answer'][s_k][t_lang_code]['answer_text']
								t_lang_result[k]['question_answer'][s_k]['rank'] = result[k]['question_answer'][s_k]['rank']
							except:
								print 'Missing Language code?', result[k]['question_answer'][s_k]

							try:
								t_lang_result[k]['question_answer'][s_k]['audio'] = result[k]['question_answer'][s_k]['en']['audio']
							except:
								print '.... NO AUDIO', k, t_lang_result[k]['question_answer'][s_k]

					if 'greetings' in v.keys():
						t_lang_result.setdefault(k, {}).setdefault('greetings', [])
						for lang_code, greetings in result[k]['greetings'].items():
							if lang_code == t_lang_code:
								for greeting in greetings:
									t_lang_result[k]['greetings'].append(greeting)


				t_json_data = json.dumps(t_lang_result)
				if not options.FLIGHTTEST:
					try:
						print '. WRITING OUTPUT', t_lang_code + '_robotspeech.json'
						with open(t_lang_code + '_robotspeech.json', 'w') as of:
							of.write(t_json_data)
						if options.OUTPUTDEST:
							f = t_lang_code + '_robotspeech.json'
							mf = os.path.join(options.OUTPUTDEST, f)
							shutil.copy2(f, mf)
					except:
						pass


		json_data = json.dumps(result)
		if not options.FLIGHTTEST:
			try:
				with open('master_robotspeech.json', 'w') as of:
					of.write(json_data)
			except:
				pass


	


	# LOCALIZE STATEMENTS
	if options.LOCALIZE:

		translate_codes = []
		translate_service = None
		if options.TRANSLATE:
			translate_service = build('translate', 'v2', developerKey=options.GOOGLEAPIKEY)
			for lang_code in options.TRANSLATE.lstrip('[').strip(']').split(','):
				translate_codes.append(lang_code.strip().lstrip())

		print '. LOADED TRANSLATION CODES', translate_codes

		to_localize = get_localize(lex)
		to_localize = dict([(_, block,) for _, block in to_localize.items() if block.is_('statement')])

		master_filename_key = os.path.splitext(options.DIALOGFILE)[0]

		if to_localize:

			print '.LOCALIZE', to_localize

			result = {}
			master_json = None
			master_fp = 'master_' + options.OUTPUTFILE
			master_pfp = 'master_' + options.OUTPUTFILE + '.bk'
			if os.path.exists(master_fp):
				with open(master_fp, 'r') as f:
					master_data = f.read()
					if master_data:
						master_json = json.loads(master_data)
						print 'Loaded Master JSON', master_json.keys()

			for block_name, rd in to_localize.items():

				# block_dir =  os.path.join(__here__, block_name)
				# try:
				#     os.makedirs(block_dir)
				# except:
				#     pass

				if hasattr(rd, 'statements'):

					for x, t in rd.statements.items():

						print 'STATEMENT', t.keys()

						do_translate = False

						result.setdefault(block_name, {}).setdefault('statements', {}).setdefault(x, {})['en'] = t['en']

						if block.is_("character") and 'actor' in t:
							result[block_name]['statements'][x]['actor'] = t['actor']

						try:
							for t_lang_code in translate_codes:
								if x in master_json[block_name]['statements']:
									if t_lang_code not in master_json[block_name]['statements'][x]:
										do_translate = True
										break
								else:
									do_translate = True
									break

							# now check to see if value changed
							if x in master_json[block_name]['statements']:
								if master_json[block_name]['statements'][x]['en'] != t['en']:
									do_translate = True

								if 'en_tts' in t:
									if master_json[block_name]['statements'][x]['en_tts'] != t['en_tts']:
										do_translate = True

								if block.is_("character") and 'actor' in t:
									if master_json[block_name]['statements'][x]['actor'] != t['actor']:
										do_translate = True
							else:
								do_translate = True

						except:
							print traceback.format_exc()
							do_translate = True

						if do_translate:

							print '+ TRANSLATE', x

							if t['en'] != None:

								# translate if needed
								if translate_service:

									for t_lang_code in translate_codes:

										attempts = 0
										while attempts < 10:
											try:

												t_res = translate_service.translations().list(
													source='en',
													target=t_lang_code,
													q=[t['en']]
												).execute()

												t_txt = t_res['translations'][0]['translatedText']
												for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
													t_txt = t_txt.replace(k_, v_)

												result[block_name]['statements'][x][t_lang_code] = t_txt

												attempts = 10 # though break should take care of this
												time.sleep(.1)
												break


											except:
												print traceback.format_exc()
												
												time.sleep(1)
												attempts += 1

								else:
									raise Exception('Localizing statements require a translation service running')

							else:
								for t_lang_code in translate_codes:
									result[block_name]['statements'][x][t_lang_code] = None

						else:

							print '. TRANSLATE', x

							for t_lang_code in translate_codes:
								result[block_name]['statements'][x][t_lang_code] = master_json[block_name]['statements'][x][t_lang_code]



			if translate_codes and translate_service:
				# translated, create lang files

				if 'en' not in translate_codes:
					translate_codes.append('en')

				for t_lang_code in translate_codes:

					t_lang_result = {}

					for k,v in result.items():

						if 'statements' in v.keys():

							t_lang_result.setdefault(k, {}).setdefault('statements', {})

							if block.is_('character'):

								# add elemnts for character, if set
								for s_k, s_v in v['statements'].items():
									try:
										t_lang_result[k].setdefault('statements', {})[s_k] = {}
										t_lang_result[k].setdefault('statements', {})[s_k]['text'] = result[k]['statements'][s_k][t_lang_code]
									except:
										print 'EXCEPTION. HALTING'
										print traceback.format_exc()
										raise

									# try to set actor if its been set
									try:
										t_lang_result[k]['statements'][s_k]['actor'] = result[k]['statements'][s_k]['actor']
									except:
										pass

									# try to set audio if its been set
									try:
										t_lang_result[k]['statements'][s_k]['audio'] = result[k]['statements'][s_k]['en']['audio']
									except:
										pass

							else:

								# no additional elements other than the text for each lang
								for s_k, s_v in v['statements'].items():
									try:
										t_lang_result[k].setdefault('statements', {})[s_k] = result[k]['statements'][s_k][t_lang_code]
									except:
										print 'EXCEPTION. HALTING'
										print traceback.format_exc()
										raise

					t_json_data = json.dumps(t_lang_result)

					if not options.FLIGHTTEST:
						try:
							with open(t_lang_code + '_%s_localized.json'%(block_name), 'w') as of:
								of.write(t_json_data)
								
							if options.OUTPUTDEST:
								f = t_lang_code + '_%s_localized.json'%(block_name)
								mf = os.path.join(options.OUTPUTDEST, f)
								shutil.copy2(f, mf)
						except:
							pass

			json_data = json.dumps(result)
			if not options.FLIGHTTEST:
				try:
					with open('master_' + options.OUTPUTFILE, 'w') as of:
						of.write(json_data)
				except:
					pass


	# LOCALIZE RECORDS (datagraph, objects)
	if options.LOCALIZE:

		print 'LOCALIZE STATEMENTS'

		master_data = None

		translate_codes = []
		translate_service = None
		if options.TRANSLATE:
			translate_service = build('translate', 'v2', developerKey=options.GOOGLEAPIKEY)
			for lang_code in options.TRANSLATE.lstrip('[').strip(']').split(','):
				translate_codes.append(lang_code.strip().lstrip())

		to_localize = get_localize(lex)
		to_localize = dict([(_, block,) for _, block in to_localize.items() if block.is_('record')])

		if to_localize:

			print '.LOCALIZE', to_localize

			result = {}
			master_json = None
			# master_fp = os.path.join(__here__, './master_localized_records.json')
			# master_pfp = os.path.join(__here__, 'master_localized_records.json.bk')
			master_fp = 'master_' + options.OUTPUTFILE
			master_pfp = 'master_' + options.OUTPUTFILE + '.bk'
			if os.path.exists(master_fp):
				with open(master_fp, 'r') as f:
					master_data = f.read()
					if master_data:
						master_json = json.loads(master_data)
						print 'Loaded Master JSON', master_json.keys()

			for block_name, rd in to_localize.items():

				# block_dir =  os.path.join(__here__, block_name)
				# try:
				#     os.makedirs(block_dir)
				# except:
				#     pass

				if hasattr(rd, 'records'):

					for x, t in rd.records.items():

						print '. KEY', x

						result.setdefault(x, {}).setdefault('en', [])
						result[x]['en'].append(t['name'])
						result[x]['en'].append(t['origin'])
						result[x]['en'].append(t['value'])
						result[x]['en'].append(t['description'])

						do_translate = False

						try:

							for t_lang_code in translate_codes:
								if t_lang_code not in master_json[x]:
									do_translate = True
									break

							if result[x]['en'] != master_json[x]['en']:
								do_translate = True

						except:
							do_translate = True

						if do_translate:

							print '+ TRANSLATE', x

							# translate if needed
							if translate_service:

								for t_lang_code in translate_codes:

									for i in range(0, 3):
										
										attempts = 0
										while attempts < 10:
											try:

												t_res = translate_service.translations().list(
													source='en',
													target=t_lang_code,
													q=[
														result[x]['en'][i]
													]
												).execute()

												t_n = t_res['translations'][0]['translatedText']
												for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
													t_n = t_n.replace(k_, v_)

												result[x].setdefault(t_lang_code, [])
												result[x][t_lang_code].append(t_n)

												attempts = 10 # though break should take care of this
												time.sleep(.1)
												break

											except:
												print traceback.format_exc()
												
												attempts += 1
												time.sleep(1*attempts)


									# now get the description sentences and translate them
									if result[x]['en'][3] != None and len(result[x]['en'][3]) > 0:

										result[x][t_lang_code].append([])

										for line in result[x]['en'][3]:
											if line:
												attempts = 0
												while attempts < 10:
													try:

														t_res = translate_service.translations().list(
															source='en',
															target=t_lang_code,
															q=line
														).execute()

														t_n = t_res['translations'][0]['translatedText']
														for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
															t_n = t_n.replace(k_, v_)

														result[x][t_lang_code][-1].append(t_n)

														attempts = 10 # though break should take care of this
														time.sleep(.1)
														break

													except:
														print traceback.format_exc()
														
														attempts += 1
														time.sleep(1*attempts)

							else:
								raise Exception('Localizing statements require a translation service running')

						else:

							print '- TRANSLATE', x
							try:
								for t_lang_code in translate_codes:
									result[x][t_lang_code] = master_json[x][t_lang_code]
							except:
								print traceback.format_exc()


							

			if translate_codes and translate_service:
				# translated, create lang files

				if 'en' not in translate_codes:
					translate_codes.append('en')

				for t_lang_code in translate_codes:

					t_lang_result = {}

					for player_data_key, data in result.items():

						t_lang_result[player_data_key] = data[t_lang_code]

						t_json_data = json.dumps(t_lang_result)

						if not options.FLIGHTTEST:
							try:
								with open(t_lang_code + '_%s_localized.json'%(block_name), 'w') as of:
									of.write(t_json_data)
								if options.OUTPUTDEST:
									f = t_lang_code + '_%s_localized.json'%(block_name)
									mf = os.path.join(options.OUTPUTDEST, f)
									shutil.copy2(f, mf)
							except:
								pass



			json_data = json.dumps(result)
			if not options.FLIGHTTEST:
				try:
					with open('master_' + options.OUTPUTFILE, 'w') as of:
						of.write(json_data)
				except:
					pass


	# LOCALIZE MENU ITEMS
	if options.LOCALIZE:

		master_data = None

		translate_codes = []
		translate_service = None
		if options.TRANSLATE:
			translate_service = build('translate', 'v2', developerKey=options.GOOGLEAPIKEY)
			for lang_code in options.TRANSLATE.lstrip('[').strip(']').split(','):
				translate_codes.append(lang_code.strip().lstrip())

		to_localize = get_localize(lex)
		to_localize = dict([(_, block,) for _, block in to_localize.items() if block.is_('option')])

		if to_localize:

			print '.LOCALIZE', to_localize

			result = {}
			master_json = None
			master_fp = 'master_' + options.OUTPUTFILE
			master_pfp = 'master_' + options.OUTPUTFILE + '.bk'
			if os.path.exists(master_fp):
				with open(master_fp, 'r') as f:
					master_data = f.read()
					if master_data:
						master_json = json.loads(master_data)
						print 'Loaded Master JSON', master_json.keys()

			for block_name, rd in to_localize.items():

				if hasattr(rd, 'menu_items'):

					rec_pos = -1

					for t in rd.menu_items:

						rec_pos += 1

						do_translate = False

						result.setdefault(block_name, {}).setdefault('menu_items', {}).setdefault('en', []).append(t)

						try:

							if master_json[block_name]['menu_items']['en'][rec_pos]['name'] != t['name']:
								raise Exception('A')

							if master_json[block_name]['menu_items']['en'][rec_pos]['description'] != t['description']:
								raise Exception('B')

							for t_lang_code in translate_codes:
								if t_lang_code not in master_json[block_name]['menu_items']:
									raise Exception('C')

						except:
							print traceback.format_exc()
							do_translate = True

						
						if do_translate or options.FORCE:

							if t != None:

								print '+ TRANSLATE', t['name']

								# translate if needed
								if translate_service:

									for t_lang_code in translate_codes:

										attempts = 0
										while attempts < 10:
											try:

												n = t['name']
												d = t['description']
												d_ = d

												place_holder_tag = "XXXXREPLACE_THIS_TAGXXXX"
												tag = None
												position = 0; # start, middle, end, no tag

												if '(' in d and ')' in d:
													# its a token
													try:
														s = d.strip()
														tag = s[s.index('('):s.index(')')+1]
														x = s.split(tag)
														d_ = d.replace(tag, place_holder_tag).strip()
													except:
														print traceback.format_exc()

												t_res = translate_service.translations().list(
													source='en',
													target=t_lang_code,
													q=[n,d_]
												).execute()

												t_n = t_res['translations'][0]['translatedText']
												d_n = t_res['translations'][1]['translatedText']

												# revert back to original if option set
												if not options.TRANSLATENAME:
													t_n = t['name']

												if place_holder_tag in d_n and tag:
													d_n = d_n.replace(place_holder_tag, tag.upper())

												for et in EMBEDDED_TRIGGERS:
													stem = ''
													if et in d:

														d_n = clean_embedded_triggers(d, et)

												d_n = d_n[0].upper() + d_n[1:]

												# replace HTML espcaped single quotes
												for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
													t_n = t_n.replace(k_, v_)
													d_n = d_n.replace(k_, v_)

												result[block_name]['menu_items'].setdefault(t_lang_code, []).append(dict(
													name=t_n,
													description=d_n
													))

												attempts = 10 # though break should take care of this
												time.sleep(.1)
												break

											except:
												print traceback.format_exc()

												if attempts == 0:
													time.sleep(60)
												
												time.sleep(1)
												attempts += 1

								else:
									raise Exception('Localizing statements require a translation service running')

							else:
								for t_lang_code in translate_codes:
									result[block_name]['menu_items'][t_lang_code] = None

						else:

							print '. TRANSLATE'

							for t_lang_code in translate_codes:
								result[block_name]['menu_items'][t_lang_code] = master_json[block_name]['menu_items'][t_lang_code]



			if translate_codes and translate_service:
				# translated, create lang files

				if 'en' not in translate_codes:
					translate_codes.append('en')

				for t_lang_code in translate_codes:

					t_lang_result = {}

					for k,v in result.items():

						if 'menu_items' in v.keys():
							t_lang_result.setdefault(k, {}).setdefault('menu_items', [])

							for d in v['menu_items'][t_lang_code]:
								try:
									t_lang_result[k].setdefault('menu_items', []).append(d)
								except:
									print 'EXCEPTION. HALTING'
									print traceback.format_exc()
									raise


					t_json_data = json.dumps(t_lang_result)

					if not options.FLIGHTTEST:
						try:
							with open(t_lang_code + '_' + options.OUTPUTFILE, 'w') as of:
								of.write(t_json_data)

							if options.OUTPUTDEST:
								f = t_lang_code + '_' + options.OUTPUTFILE
								mf = os.path.join(options.OUTPUTDEST, f)
								shutil.copy2(f, mf)

								print '. COPIED', mf
						except:
							pass

			json_data = json.dumps(result)
			if not options.FLIGHTTEST:
				try:
					with open('master_' + options.OUTPUTFILE, 'w') as of:
						of.write(json_data)

					# if options.OUTPUTDEST:
					#     f = 'en_' + options.OUTPUTFILE
					#     mf = os.path.join(options.OUTPUTDEST, f)
					#     shutil.copy2(f, mf)

				except:
					pass


	
	if options.VERBOSE:
		print '. STORY OUTPUT'
		pprint.pprint(story)

	
	if story:

		global translate_codes, translate_service


		master_json = None
		try:
			with open('master_' + options.OUTPUTFILE, 'r') as f:
				master_data = f.read()
				if master_data:
					master_json = json.loads(master_data)
					print 'Loaded Master JSON', master_json.keys()
		except:
			print traceback.format_exc()
			if not options.FORCE:
				print 'Exiting....'
				sys.exit()


		result = {}

		if 'en' not in translate_codes:
			translate_codes.append('en')

		if translate_codes and translate_service:
			# translated, create lang files

			for t_lang_code in translate_codes:

				t_lang_result = {}

				if 'main_storyline' in story:
					t_lang_result.setdefault('main_storyline', [])

					sb_pos = -1

					for sb in story['main_storyline']:

						sb_pos += 1

						t_sb = copy.deepcopy(sb)

						translate = False
						try:
							if master_json:
								if master_json['en']['main_storyline'][sb_pos]['incoming'] != sb['incoming']:
									raise Exception("Incoming doesn't match")

								if set(master_json['en']['main_storyline'][sb_pos]['responses']) != set(sb['responses']):
									raise Exception("Responses don't match")

								if 'segue' in sb:
									if master_json['en']['main_storyline'][sb_pos]['segue'] != sb['segue']:
										raise Exception("Segue doesn't match")

								t_sb = copy.deepcopy(master_json[t_lang_code]['main_storyline'][sb_pos])

							else:
								raise Exception("No Master File")
						except:
							print traceback.format_exc()
							translate = True

						print '. SHOULD TRANSLATE', translate

						if t_lang_code != 'en':
							if translate or options.FORCE:

								if 'segue' in sb:
									# translate the segue
									s_txt = sb['segue']

									print '.TRANSLATE SEQUE'

									try:
										attempts = 0
										while attempts < 10:
											try:

												t_res = translate_service.translations().list(
													source='en',
													target=t_lang_code,
													q=[s_txt]
												).execute()

												t_n = t_res['translations'][0]['translatedText']
												for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
													t_n = t_n.replace(k_, v_)

												t_sb['segue'] = t_n

												attempts = 10 # though break should take care of this
												time.sleep(.15)
												break

											except:
												print traceback.format_exc()

												if attempts == 0:
													time.sleep(60)
												
												attempts += 1
												time.sleep(.2*attempts)
									except:
										print traceback.format_exc()


								# translate the incoming
								i_txt = sb['incoming']

								print '+ TRANSLATE INCOMING', i_txt

								try:
									attempts = 0
									while attempts < 10:
										try:

											place_holder_tag = "XXXXREPLACE_THIS_TAGXXXX"
											tag = None
											position = 0; # start, middle, end, no tag

											if '<' in i_txt and '>' in i_txt:
												# its a token
												try:
													s = i_txt.strip()
													tag = s[s.index('<'):s.index('>')+1]
													x = s.split(tag)
													i_txt = i_txt.replace(tag, place_holder_tag).strip()
												except:
													print traceback.format_exc()

											t_res = translate_service.translations().list(
												source='en',
												target=t_lang_code,
												q=[i_txt]
											).execute()

											t_result = t_res['translations'][0]['translatedText']
											if tag:
												t_result = t_result.replace(place_holder_tag, tag)


											for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
												t_result = t_result.replace(k_, v_)

											t_sb['incoming'] = t_result

											attempts = 10 # though break should take care of this
											time.sleep(.15)
											break

										except:
											print '. T_RESULT', t_result
											print traceback.format_exc()

											if attempts == 0:
												time.sleep(60)
											
											attempts += 1
											time.sleep(.2*attempts)
								except:
									print traceback.format_exc()


								# translate the response
								r_txts = sb['responses']
								t_sb['responses'] = []
								for r_txt in r_txts:

									print '.TRANSLATE RESPONSE', r_txt

									try:
										attempts = 0
										while attempts < 10:
											try:

												t_res = translate_service.translations().list(
													source='en',
													target=t_lang_code,
													q=[r_txt]
												).execute()

												t_txt = t_res['translations'][0]['translatedText']
												for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
													t_txt = t_txt.replace(k_, v_)

												t_sb['responses'].append(t_txt)

												attempts = 10 # though break should take care of this
												time.sleep(.15)
												break

											except:
												print traceback.format_exc()

												if attempts == 0:
													time.sleep(60)
												
												attempts += 1
												time.sleep(1.2*attempts)
									except:
										print traceback.format_exc()


						t_lang_result['main_storyline'].append(t_sb)


				if 'dynamic_storyline' in story:
					t_lang_result.setdefault('dynamic_storyline', [])

					sb_pos = -1

					for sb in story['dynamic_storyline']:

						sb_pos += 1

						t_sb = copy.deepcopy(sb)

						translate = False
						try:
							match = False
							for m_sb in master_json["en"]['dynamic_storyline']:

								# t_sb = copy.deepcopy(m_sb)

								if m_sb['player_data_key'] == sb['player_data_key']:
									match = True
									if m_sb['response'] != sb['response']:
										raise Exception("Dynamic repsones doesn't match")

									d_m_sb_pos = -1
									for d_m_sb in m_sb['dynamic_storyline']:
										d_m_sb_pos += 1
										if d_m_sb['incoming'] != sb['dynamic_storyline'][d_m_sb_pos]['incoming']:
											raise Exception("Dynamic incoming doesn't match")

										if set(d_m_sb['responses']) != set(sb['dynamic_storyline'][d_m_sb_pos]['responses']):
											raise Exception("Dynamic responses doesn't match")

							if not match:
								raise Exception("No Match")

						except:
							print 'EXCEPTION HERE', traceback.format_exc()
							translate = True

						print '. SHOULD TRANSLATE DYNAMIC', translate, sb['player_data_key']

						if t_lang_code != 'en':

							if translate or options.FORCE:

								# translate the response
								r_txt = t_sb['response']

								try:
									attempts = 0
									while attempts < 10:
										try:

											t_res = translate_service.translations().list(
												source='en',
												target=t_lang_code,
												q=[r_txt]
											).execute()

											t_txt = t_res['translations'][0]['translatedText']
											for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
												t_txt = t_txt.replace(k_, v_)
											t_sb['response'] = t_txt

											attempts = 10 # though break should take care of this
											time.sleep(.15)
											break

										except:
											print traceback.format_exc()

											if attempts == 0:
												time.sleep(60)
											
											attempts += 1
											time.sleep(1.2*attempts)
								except:
									print traceback.format_exc()


								for dynamic in t_sb['dynamic_storyline']:

									# translate incoming
									i_txt = dynamic['incoming']

									print '.TRANSLATE DYNAMIC INCOMING', i_txt

									try:
										attempts = 0
										while attempts < 10:
											try:

												t_res = translate_service.translations().list(
													source='en',
													target=t_lang_code,
													q=[i_txt]
												).execute()

												t_txt = t_res['translations'][0]['translatedText']
												for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
													t_txt = t_txt.replace(k_, v_)

												dynamic['incoming'] = t_txt

												attempts = 10 # though break should take care of this
												time.sleep(.15)
												break

											except:
												print traceback.format_exc()

												if attempts == 0:
													time.sleep(60)
											
												attempts += 1
												time.sleep(1.2*attempts)
									except:
										print traceback.format_exc()

									responses = dict()

									try:
										responses = copy.copy(dynamic['responses'])
									except:
										print traceback.format_exc()
										print str(t_sb)
										print
										sys.exit()

									dynamic['responses'] = []

									for r_txt in responses:

										print '.TRANSLATE RESPONSE OPTION', r_txt

										# translate responses
										try:
											attempts = 0
											while attempts < 10:
												try:

													t_res = translate_service.translations().list(
														source='en',
														target=t_lang_code,
														q=[r_txt]
													).execute()

													t_txt = t_res['translations'][0]['translatedText']
													for k_,v_ in TRANSLATED_HTML_ESCAPES.items():
														t_txt = t_txt.replace(k_, v_)

													dynamic['responses'].append(t_txt)

													attempts = 10 # though break should take care of this
													time.sleep(.15)
													break

												except:
													print traceback.format_exc()

													if attempts == 0:
														time.sleep(60)
													
													attempts += 1
													time.sleep(1.2*attempts)
										except:
											print traceback.format_exc()

						t_lang_result['dynamic_storyline'].append(t_sb)
						

				t_json_data = json.dumps(t_lang_result)

				result[t_lang_code] = t_lang_result

				if options.VERBOSE:
					print '. TRANSLATED OUTPUT'
					print 
					pprint.pprint(t_json_data)
					print

				if not options.FLIGHTTEST and options.OUTPUTFILE:
					try:
						with open(t_lang_code + '_' + options.OUTPUTFILE, 'w') as of:
							of.write(t_json_data)

						if options.OUTPUTDEST:
							f = t_lang_code + '_' + options.OUTPUTFILE
							mf = os.path.join(options.OUTPUTDEST, f)
							shutil.copy2(f, mf)
					except:
						pass


		# dump the story
		# djson = json.dumps(story)
		djson = json.dumps(result)

		if not options.FLIGHTTEST and options.OUTPUTFILE:
			try:
				with open('master_' + options.OUTPUTFILE, 'w') as of:
					of.write(djson)

				if options.OUTPUTDEST:
					f = 'master_' + options.OUTPUTFILE
					mf = os.path.join(options.OUTPUTDEST, f)
					shutil.copy2(f, mf)
			except:
				pass


	return True
	
	
def parseArgs(args=None):

	# translate_api_key_1 AIzaSyD6VFxzb0EAjzX4iUrW2GFv5BX8147n-ec

	# python dialogc.py -d robotdialog.yaml --robot-voice-gen --only-en-rvg --translate [fr,es,it,ca,de,ja,zh-CN,ru,ko] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E --cereproc-api-key 5669b86be50d7 --cereproc-api-psswrd r9gTHn6cZa --output-dest ../Assets/Resources/JSON
	# python dialogc.py -d acuity.yaml --localize --translate [fr,es,it,ca,de,ja,zh-CN,ru,ko] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E -o Acuity.json --output-dest ../Assets/Resources/JSON
	# python dialogc.py -d characterdialog.yaml --localize --translate [fr,es,it,ca,de,ja,zh-CN,ru,ko] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E -o InteractiveCharacterDialog.yaml --output-dest ../Assets/Resources/JSON
	# python dialogc.py -d datagraph.yaml --localize --translate [fr,es,it,ca,de,ja,zh-CN,ru,ko] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E -o DatagraphObjects.json --output-dest ../Assets/Resources/JSON
	# python dialogc.py -d computer_options.yaml --localize --translate [fr,es,it,ca,de,ja,zh-CN,ru,ko] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E -o ComputerInterfaceOptions.json --output-dest ../Assets/Resources/JSON
	# python dialogc.py -d dialog.yaml --include-dyn --include-main --localize --translate [fr,es,it,ca,de,ja,zh-CN,ru,ko] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E -o ComputerInterfaceDialogue.json --output-dest ../Assets/Resources/JSON
	# python dialogc.py -d uielements.yaml --localize --translate [fr,es,it,ca,de,ja,zh-CN,ru,ko] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E -o UIElements.json --output-dest ../Assets/Resources/JSON
	
	# python dialogc.py -d test_datagraph2.yaml --localize --translate [fr,es,it,ca,de,ja,zh-CN] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E
	# python dialogc.py -d test_uielements.yaml --localize --translate [fr] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E
	# python dialogc.py -d test_computer_options.yaml --localize --translate [fr] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E -o ComputerInterfaceOptions.json
	# python dialogc.py -d test_robotdialog.yaml --robot-voice-gen --only-en-rvg --translate [fr,es,it,ca,de,ja,zh-CN,ru,ko] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E --cereproc-api-key 5669b86be50d7 --cereproc-api-psswrd r9gTHn6cZa --output-dest ../Assets/Resources/JSON

	# python dialogc.py -d dialog.yaml --include-vox --translate [fr,es,it,ca,de,ja,zh-CN] --google-api-key AIzaSyDRr-K3lO_m_Dp0V7agzNRx5Snq6Grio7E
	# [Q8DrillingSafetyBot,GameHostBot,MainQuartersRobot,ProcessingSafetyBot,Q8MillingSafetyBot,HibernationRobot,CentralAI,Q8ProcessingSafetyBot,MillingSafetyBot,DrillingSafetyBot,LabSecurityBot,LabCompanionBot]
	# [Q8DrillingSafetyBot,GameHostBot,MainQuartersRobot,ProcessingSafetyBot,Q8MillingSafetyBot,HibernationRobot,Q8ProcessingSafetyBot,MillingSafetyBot,DrillingSafetyBot,LabSecurityBot,LabCompanionBot]

	parser = OptionParser()

	parser.add_option("-d", dest="DIALOGFILE", help="Dialog file")
	parser.add_option("-o", dest="OUTPUTFILE", help="Output file")
	parser.add_option("-s", dest="SCRIPTOUTPUTFILE", help="Script Output file")
	parser.add_option("-v", action="store_true", default=False, dest="VERBOSE", help="Verbose")
	parser.add_option("--print-footer", action="store_true", default=False, dest="PRINTFOOTER", help="Print Footer")
	parser.add_option("--include-main", action="store_true", default=False, dest="INCLUDEMAIN", help="Include main conversation")
	parser.add_option("--include-dyn", action="store_true", default=False, dest="INCLUDEDYN", help="Include all dynamic conversations")
	parser.add_option("--include-aux", action="store_true", default=False, dest="INCLUDEAUX", help="Include all auxilary, supporting text")
	parser.add_option("--include-vox", action="store_true", default=False, dest="INCLUDEVOX", help="Include spoken dialog")
	parser.add_option("--output-x-character", action="store_true", default=False, dest="OUTPUTXCHAR", help="Output script files for each character")
	parser.add_option("--robot-voice-gen", action="store_true", default=False, dest="ROBOTVOICEGEN", help="Output Robot Voice Files")
	parser.add_option("--only-en-rvg", action="store_true", default=False, dest="ONLYENROBOTVOICEGEN", help="Only Output Robot Voice Files in English")
	parser.add_option("--google-api-key", dest="GOOGLEAPIKEY", help="Google API Key")
	parser.add_option("--cereproc-api-key", dest="CEREPROCAPIKEY", help="Cere Proc API Key")
	parser.add_option("--cereproc-api-psswrd", dest="CEREPROCAPIPSSWRD", help="Cere Proc API Password")
	parser.add_option("--translate", dest="TRANSLATE", help="Languages to Translate")
	parser.add_option("--localize", action="store_true", default=False, dest="LOCALIZE", help="Translate LOCALIZE formatted DialogC blocks")
	parser.add_option("--localize-names", action="store_false", default=True, dest="TRANSLATENAME", help="Translate Item Names")
	parser.add_option("--only-blocks", dest="ONLYBLOCKS", help="Process Only These Blocks")
	parser.add_option("--ignore-blocks", dest="IGNOREBLOCKS", help="Ignore Only These Blocks")
	parser.add_option("--regen-blocks", dest="REGENBLOCKS", help="Regenerate These Blocks")
	parser.add_option("--regen-block-categories", dest="REGENBLOCKCATS", help="Regenerate These Block Categories")
	parser.add_option("--only-pdks", dest="ONLYPDKS", help="Process Only These Player Data Keys")
	parser.add_option("--ogg-to-wav", action="store_true", default=True, dest="OGGTOWAV", help="Convert Oggs to Wavs")
	parser.add_option("--wav-to-ogg", action="store_true", default=False, dest="WAVTOOGG", help="Convert Wavs to Ogg")
	parser.add_option("--flighttest", action="store_true", default=False, dest="FLIGHTTEST", help="Run a Flight Test")
	parser.add_option("--output-dest", dest="OUTPUTDEST", help="Move output file to dest")
	parser.add_option("--force", action="store_true", default=False, dest="FORCE", help="Force overwrite if no master")

	(options, args) = parser.parse_args()
	
	if options != None:
		return options
		
		
if __name__ == '__main__':

	print 'starting dialogc'

	options = parseArgs()

	only_blocks = []
	ignore_blocks = []
	regen_block_categories = []
	translate_codes = []
	translate_service = None


	if options.TRANSLATE:
		translate_service = build('translate', 'v2', developerKey=options.GOOGLEAPIKEY)
		for lang_code in options.TRANSLATE.lstrip('[').strip(']').split(','):
			translate_codes.append(lang_code.strip().lstrip())

	if options.ONLYBLOCKS:
		for x in options.ONLYBLOCKS.lstrip('[').strip(']').split(','):
			only_blocks.append(x.strip().lstrip())

	if options.IGNOREBLOCKS:
		for x_ in options.IGNOREBLOCKS.lstrip('[').strip(']').split(','):
			ignore_blocks.append(x_.strip().lstrip())

	if options.REGENBLOCKCATS:
		for x_ in options.REGENBLOCKCATS.lstrip('[').strip(']').split(','):
			regen_block_categories.append(x_.strip().lstrip())

	r = doit()
	
	print 'done'

   
	
	
	
	