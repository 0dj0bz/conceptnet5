"""
Parse the ReVerb dataset and put assertions to ConceptNet 5
"""
from conceptnet5.graph import get_graph
from conceptnet5.english_nlp import normalize, tokenize, untokenize
from urlparse import urlparse
import codecs
import nltk
import os
import re

GRAPH = get_graph()

reverb = GRAPH.get_or_create_node(u'/source/rule/reverb')
GRAPH.justify(0, reverb)
reverb_object = GRAPH.get_or_create_node(u'/source/rule/extract_reverb_objects')
reverb_triple = GRAPH.get_or_create_node(u'/source/rule/reverb_present_tense_triples')
wikipedia = GRAPH.get_or_create_node(u'/source/web/en.wikipedia.org')
GRAPH.justify(0, reverb_object)
GRAPH.justify(0, reverb_triple)
GRAPH.justify(0, wikipedia)

TYPE_WORDS = ('type', 'kind', 'sort', 'variety')

# Search for non-namespaced Wikipedia sources.
WIKIPEDIA_SOURCE = re.compile(r'(http://en.wikipedia.org/wiki/([^:]|:_)+)(\||$)')

def probably_present_tense(text):
    return text in ('is', 'are') or normalize(text) == text

def contain_single_be(tokens, tags):
    be = ['is', 'are', 'was', 'were', 'be']
    verbs = filter(lambda x: x.startswith('V'), tags)
    if len(verbs) == 1 and tokens[tags.index(verbs[0])] in be:
        return tags.index(verbs[0])
    elif len(verbs) == 2 and tokens[tags.index(verbs[1])] == 'been':
        return tags.index(verbs[1])
    return -1

def index_of_tag(tags, target):
    if target in tags:
        return tags.index(target)
    return -1

def index_of_be(tokens):
    be = ['is', 'are', 'was', 'were', 'be', 'been']
    for token in tokens:
        if token in be:
            return tokens.index(token)
    return -1

def index_of_verbs(tags):
    index = []
    for tag in tags:
        if tag.startswith('V'):
            index.append(tags.index(tag))
    return index

def remove_tags(tokens, tags, target):
    index_rb = 0
    if target in tags:
        index_rb = tags.index(target)
    if index_rb > 0:
      tokens.remove(tokens[index_rb])
      tags.remove(tags[index_rb])
    return tokens, tags

def get_domain_names(urls):
    parsed_urls = map(lambda x: urlparse(x), urls)
    domain_names = map(lambda x: x.netloc, parsed_urls)
    return domain_names

def output_triple(arg1, arg2, relation, raw):
    arg1 = normalize(arg1).strip()
    arg2 = normalize(arg2).strip()
    relation = normalize(relation).strip()

    assertion = GRAPH.get_or_create_assertion(
        GRAPH.get_or_create_concept('en', relation),
        [GRAPH.get_or_create_concept('en', arg1),
         GRAPH.get_or_create_concept('en', arg2)],
        {'dataset': 'reverb/en', 'license': 'CC-By-SA'}
    )
    GRAPH.derive_normalized(raw, assertion)
    
    conjunction = GRAPH.get_or_create_conjunction([raw, reverb_triple])
    GRAPH.justify(conjunction, assertion)
    print assertion['uri']
    return assertion

def output_raw(raw_arg1, raw_arg2, raw_relation, sources):
    frame = u"{1} %s {2}" % (raw_relation)
    raw = GRAPH.get_or_create_assertion(
        GRAPH.get_or_create_frame('en', frame),
        [GRAPH.get_or_create_concept('en', raw_arg1),
         GRAPH.get_or_create_concept('en', raw_arg2)],
        {'dataset': 'reverb/en', 'license': 'CC-By-SA',
         'sources': '|'.join(sources)}
    )
    
    # Turns out that only en.wikipedia.org matters as a domain. The rest are
    # all mirrors.
    conjunction = GRAPH.get_or_create_conjunction([wikipedia, reverb])
    
    # The assertions start with numbers are really bad in ReVerb.
    # We set a small weight on the justification edge, if we include
    # them at all.
    if raw_arg1[0].isdigit():
        GRAPH.justify(conjunction, raw, weight=0.2)
    else:
        GRAPH.justify(conjunction, raw, weight=0.7)
    print raw['uri']
    return raw

def output_sentence(arg1, arg2, arg3, relation, raw, prep=None):
    if arg2.strip() == "": # Remove "A is for B" sentence
        return
    arg1 = normalize(arg1).strip()
    arg2 = normalize(arg2).strip()
    assertion = None
    if arg3 == None:
        print '%s(%s, %s)' % (relation, arg1, arg2)
        assertion = GRAPH.get_or_create_assertion(
            '/relation/'+relation,
            [GRAPH.get_or_create_concept('en', arg1),
             GRAPH.get_or_create_concept('en', arg2)],
            {'dataset': 'reverb/en', 'license': 'CC-By-SA'}
        )
        assertions = (assertion,)
    else:
        if arg3.strip() == "": # Remove "A before/after/off" sentence
            return
        arg3 = normalize(arg3).strip()
        print '%s(%s, %s), %s(%s, %s)' % \
            (relation, arg1, arg2, prep, arg2, arg3)
        assertion1 = GRAPH.get_or_create_assertion(
            '/relation/'+relation,
            [GRAPH.get_or_create_concept('en', arg1),
             GRAPH.get_or_create_concept('en', arg2)],
            {'dataset': 'reverb/en', 'license': 'CC-By-SA'}
        )
        assertion2 = GRAPH.get_or_create_assertion(
            GRAPH.get_or_create_concept('en', prep),
            [GRAPH.get_or_create_concept('en', arg2),
             GRAPH.get_or_create_concept('en', arg3)],
            {'dataset': 'reverb/en', 'license': 'CC-By-SA'}
        )
        assertions = (assertion1, assertion2)

    for assertion in assertions:
        GRAPH.derive_normalized(raw, assertion)
        print assertion['uri']

    return assertion

def handle_file(filename):
    import traceback
    for line in codecs.open(filename, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line:
            try:
                handle_line(line)
            except:
                traceback.print_exc()

def handle_line(line):
    parts = line.split('\t')
    if len(parts) < 10:
        return
    id, old_arg1, old_rel, old_arg2, nor_arg1, nor_rel, nor_arg2, \
        num_sentence, confidence, url = parts
    # Rob put this in: skip all the numeric ones for now, our time
    # is better spent on others
    if old_arg1[0].isdigit() or old_arg2[0].isdigit():
        return
    sources = [match[0] for match in WIKIPEDIA_SOURCE.findall(url)]
    if not sources:
        return
    
    sentence = "%s %s %s" % (old_arg1, old_rel, old_arg2)
    tokens = nltk.word_tokenize(sentence)
    tags = map(lambda x: x[1], nltk.pos_tag(tokens))
    tokens, tags = remove_tags(tokens, tags, 'RB')	# Remove adverb
    tokens, tags = remove_tags(tokens, tags, 'MD')	# Remove modals
    tokens = map(lambda x: x.lower(), tokens)

    raw = output_raw(old_arg1, old_arg2, old_rel, sources)
    triple = output_triple(old_arg1, old_arg2, old_rel, raw)

    index_verbs = index_of_verbs(tags)
    if len(index_verbs) == 0: return
    index_be = contain_single_be(tokens, tags)
    if index_be == len(tokens) - 1: return
    index_prep = 0
    if 'IN' in tags:
        if tags.index('IN') > index_verbs[0]:
            index_prep = tags.index('IN')
    if 'TO' in tags:
        index_to = tags.index('TO')
        if ((index_to < index_prep and index_prep > 0) or \
            (index_prep == 0)) and (index_to > index_verbs[0]):
            index_prep = tags.index('TO')
    if index_be > 0:
        if tokens[index_be] == 'been':
            arg1 = untokenize(tokens[:index_be-1])
        else:
            arg1 = untokenize(tokens[:index_be])
        next_tag = tags[index_be+1]
        if next_tag == 'DT': # IsA relation
            if index_prep == 0:
                arg2 = untokenize(tokens[index_be+2:])
                output_sentence(arg1, arg2, None, 'IsA', raw)
            else:
                if tokens[index_prep] == 'of' and \
                    tokens[index_prep-1] in TYPE_WORDS:
                    # 'a kind of' frame
                    arg2 = untokenize(tokens[index_prep+1:])
                    output_sentence(arg1, arg2, None, 'IsA', raw)
                elif tokens[index_prep] == 'of' and \
                    tokens[index_prep-1] == 'part':
                    # 'a part of' frame
                    arg2 = untokenize(tokens[index_prep+1:])
                    output_sentence(arg1, arg2, None, 'PartOf', raw)
                else:
                    arg2 = untokenize(tokens[index_be+2:index_prep])
                    arg3 = untokenize(tokens[index_prep+1:])
                    output_sentence(arg1, arg2, arg3, 'IsA', raw,
                        prep=tokens[index_prep])
        else: # HasProperty relation
            if index_prep == 0:
                arg2 = untokenize(tokens[index_be+1:])
                output_sentence(arg1, arg2, None, 'HasProperty', raw)
            else:
                arg2 = untokenize(tokens[index_be+1:index_prep])
                arg3 = untokenize(tokens[index_prep+1:])
                output_sentence(arg1, arg2, arg3, 'HasProperty', raw,
                    prep=tokens[index_prep])
    else:
        index_be = index_of_be(tokens)
        if index_be == len(tokens) - 1: return
        if (index_be > 0) and \
            (index_verbs[0] == index_be or \
            len(index_verbs) > 1): 
            if tokens[index_be] == 'been':
                arg1 = untokenize(tokens[:index_be-1])
            else:
                arg1 = untokenize(tokens[:index_be])
            if tags[index_be+1] == 'VBG': 
                relation = 'SubjectOf'
            else: 
                relation = 'DirectObjectOf'
            if index_prep == 0:
                arg2 = untokenize(tokens[index_be+1:])
                output_sentence(arg1, arg2, None, relation, raw)
            else:
                arg2 = untokenize(tokens[index_be+1:index_prep])
                arg3 = untokenize(tokens[index_prep+1:])
                output_sentence(arg1, arg2, arg3, relation, raw,
                    prep=tokens[index_prep])
        else: # SubjectOf relation
            if index_prep > 0:
                arg1 = untokenize(tokens[:index_verbs[0]])
                arg2 = untokenize(tokens[index_verbs[0]:index_prep])
                arg3 = untokenize(tokens[index_prep+1:])
                output_sentence(arg1, arg2, arg3, 'SubjectOf', raw,
                    prep=tokens[index_prep])

if __name__ == '__main__':
    import sys
    for filename in sys.argv[1:]:
        if filename.startswith('reverb'):
            handle_file(filename)
