'''

   Lexicon-Based Sentiment Analysis Library

   Performs sentiment classification on input
   documents with the assistance of sentiment lexicons.

'''

import re
import math
import nltk.stem
import collections

# library imports
import sentlex
import negdetect
import stopwords
from docscoreutil import *


class DocSentiScore(object):
    '''
     DocSentiScore

     This class performs lexicon-based sentiment classification on an input document
     given a set of parameters that configure the classification algorithm.
    '''

    def __init__(self):
        # initialize the default stopwords list
        self.objectiveWords = stopwords.Stopword()
        # default configuration
        self.set_active_pos(True, True, False, False)
        self.set_neg_detection(True)
        self.L = None
        self.verbose = False
        self.resultdata = {}

    def classify_document(self, Doc, tagged=True, verbose=True, **kwargs):
        '''
         Classify an input document with classifier parameters per kwargs.
           Doc - string, inoput document.
           tagged - indicate wheter document is POS-tagged (False will call NLTK's default tagger)
           verbose - debug messages printed.
           **kwargs - classifier-specific parameters (optional). 

         When subclassing the default classifier, classify_doc (the algorithm)
         and set_parameters (parse algo parameters) need to be implemented.

         The following are mandatory parameters for every classifier algorithm:
           L - a sentiment lexicon (sentlex.Lexicon object);
           a,v,r,n - POS tags to scan (booleans);
           negation - boolean
           negation_window - integer
        '''
        raise NotImplementedError

    def set_parameters(self, **kwargs):
        '''
         sets runtime parameters for this classification algorithm
        '''
        raise NotImplementedError

    def set_lexicon(self, newL):
        assert newL.is_loaded, 'Lexicon must be loaded before use.'
        self.L = newL

    def _detect_tag(self, Doc):
        '''
         For an input doc, detect POS separator (Brown or UPenn), if any, based on first 3 tokens.
         Returns None if no consistent match is found.
        '''
        def check_sep(sep, tokens):
            # does my separator generates tuples?
            seplist = [nltk.tag.str2tuple(i, sep=sep)[1] for i in tokens]
            if None in seplist:
                return None
            return sep

        tokens = Doc.split()
        mintags = min(3, len(tokens))
        tokens = tokens[:mintags]
        for i in ['/', '_']:
            separator = check_sep(i, tokens)
            if separator: return separator

        return None 

    def pos_tag(self, Doc):
        '''
         Returns POS-tagged document using NLTK's recommended tagger.
        '''
        return ' '.join([x[0]+'/'+x[1] for x in nltk.pos_tag(nltk.word_tokenize(Doc))])

    def _debug(self, msg):
        if self.verbose: print msg


class BasicDocSentiScore(DocSentiScore):
    '''
      BasicDocSentiScore
      This class implements algorithm that scans and sums sentiment scores
      found in the document, based on a sentiment lexicon.

      The default parameters (pos, negation) affect this algorithm.

      In addition, 2 more tunable parameters can be used:
      - scan mode: how to add sentiment data from lexicons (once, always, frequency-adjusted)
      - weight function: function to adjust scores based on location within document.
        (some basic functions are supplied in the class, but they can be user defined)

    '''

    def __init__(self):
        # calls superclass
        super(BasicDocSentiScore,self).__init__()
        # Constants driving term-counting behavior 
        self.SCOREALL = 0
        self.SCOREONCE = 1
        # default configuration for Basic
        self.score_mode = self.SCOREALL
        self.score_freq = False
        self.score_stop = False
        self.score_function = self._score_noop
        self.negated_term_adj = 0.0
        # Setup stem preprocessing for verbs
        self.wnl = nltk.stem.WordNetLemmatizer()

    def set_neg_detection(self, mode, window=5, negated_adj=0.0):
        '''
         Enable negation detection for this algorithm
        '''
        self.negation = mode
        self.negation_window = window
        self.negated_term_adj = negated_adj

    def set_active_pos(self, a=True, v=True, n=False, r=False):
        '''
         determine which POS tags to apply during classification
        '''
        self.a = a
        self.v = v
        self.n = n
        self.r = r

    #
    # Lexicon Based Classification Engine
    # - the methods in this section can be overriden to implement technique variations for lex-based classifiers
    #
    def _negation_calc(self, tags, window):
        '''
         for a list of tokens, calculate array of negated words based on a negation detection
         algorithm (NegEx in our case).
         returns arran vNEG containing [0,1] for each index of token on original tags list, indicating negation.
        '''
        vNEG = negdetect.getNegationArray(tags, window)
        return vNEG

    def _get_word_contribution(self, thisword, tagword, scoretuple, i, doclen):
        '''
         Returns tuple (posval, negval) containing score contribution for i-th word in document, based
         on algorithm setup and scoretuple retrieved from lexicon.
        '''
        posval = 0.0
        negval = 0.0
        # Negation detection: flip indexes for pos/neg values if negated word
        if self.negation:
            posindex = self.vNEG[i-1]
            negindex = (1+self.vNEG[i-1])%2
        else:
            posindex = 0
            negindex = 1

        # self.SCOREALL: counts all word ocurrences
        # self.SCOREONCE: counts each word/POS combination only once. Keeps track in self.tag_counter
        if (
             (
              (self.score_mode == self.SCOREALL) or 
              (self.score_mode == self.SCOREONCE and (tagword not in self.tag_counter))
             )
             and
             ( 
              (self.score_stop and (not self.objectiveWords.is_stop(thisword))) or
              (not self.score_stop)
             )
           ):
            posval = self.score_function(scoretuple[posindex], i, doclen)
            negval = self.score_function(scoretuple[negindex], i, doclen)
            if self.score_freq:
                # Scoring with frequency information
                # Frequency is a real valued at 0.0-1.0. We calculate sqrt function so that the value grows faster even for numbers close to 0 
                posval *= 1.0 - max(math.sqrt(self.L.get_freq(thisword)), 0.25)
                negval *= 1.0 - max(math.sqrt(self.L.get_freq(thisword)), 0.25)
            self._debug('[_get_word_contribution] word %s (%s) at %d-th place on docsize %d is eligible (%2.2f, %2.2f).' % (thisword, str(scoretuple), i, doclen, posval, negval))

        return (posval, negval)


    def _doc_score_adjust(self, posval, negval):
        '''
         Final adjustments to doc scoring once scan completes
        '''
        return (posval, negval)


    def _reset_runtime_vars(self):
        self.vNEG = []
        self.resultdata = {}
        self.tag_counter = collections.Counter()


    def classify_document(self, Doc, tagged=True, verbose=False, **kwargs):
        '''
         Performs lexicon-based sentiment classification of input document.
         Doc is a POS-tagged document, which can optionally be tagged on-the-fly when tagged=False.
         **kwards are parameter settings for this algorithm. (optional)

         In addition to default parameters, this class accepts the following
         as tunables for this algorithm:
          - score_mode: one of SCOREALL/ONCE
          - score_freq: enable frequency-adjusted scores
          - score_stop: enable stop-word detection (stop words are discarded, override what lexicon may say)

         Returns: (pos_Score, neg_score) - total scores obtained from the scan.

        '''
        # Process input parameters, if any
        self.set_parameters(**kwargs)
        self.verbose = verbose
        assert self.L and self.L.is_loaded, 'Lexicon has not been assigned, or not loaded'

        # POS-taging and tag detection
        if not tagged:
            tagged_doc = self.pos_tag(Doc)
        else:
            tagged_doc = Doc
        tagsep = self._detect_tag(tagged_doc)
        assert tagsep, 'Unable to detect tag separator'

        # ready to start - reset runtime vars
        self._reset_runtime_vars()
        self._debug('[classify_document] - tag separator is %s' % tagsep)
        tags = tagged_doc.split()
        annotatedTags = []
        doclen = len(tags)
        i = 0
        postotal = 0.0
        negtotal = 0.0
        foundcounter = 0
        negcount = 0
        self.tag_counter = collections.Counter()
        tagUnscored = []
 
        # Negation detection pre-processing - return an array w/ position of negated terms
        self.vNEG = self._negation_calc(tags, self.negation_window)

        # Scan for scores for each POS
        # After POS-tagging a term will appear as either term/POS or term_POS
        # We assume such weirdnesses will not naturally occur on plain text.
        for tagword in tags:
            i+=1
            scoretuple = (0,0)
            tagfound = False
            # retrieves tuple (word, POS tag) from current word+tag string
            (thisword, thistag) = nltk.tag.str2tuple(tagword, sep=tagsep)
            if (not thistag) or (not thisword):
                continue  # discard corrupt data
            thisword = thisword.lower()

            # Adjectives 
            if self.a and re.search('(JJ|JJ.)$', thistag):
                tagfound = True
                scoretuple = self.L.getadjective(thisword)

            # Verbs (VBP / VBD/ etc...)
            if self.v and re.search('(VB|VB.)$', thistag):
                tagfound = True
                thislemma = self.wnl.lemmatize(thisword, pos='v')
                scoretuple = self.L.getverb(thislemma)
          
            # Adverbs
            if self.r and re.search('RB$', thistag):
                tagfound = True
                scoretuple = self.L.getadverb(thisword)

            # Nouns
            if self.n and re.search('NN$', thistag):
                tagfound = True
                scoretuple = self.L.getnoun(thisword)

            #
            # Add this word contribution to total
            #
            if tagfound:
                (posval, negval) = self._get_word_contribution(thisword, tagword, scoretuple, i, doclen)
                postotal += posval
                negtotal += negval
                self._debug('Running total (pos,neg): %2.2f, %2.2f'%(postotal,negtotal))

                # Found a tag - increase counters and add tag to list
                self.tag_counter.update([tagword])
                if scoretuple == (0,0): tagUnscored.append(tagword)
                foundcounter += 1
                if self.negation and self.vNEG[i-1]==1:
                    negcount += 1
                if self.negation: 
                    negtag = str(self.vNEG[i-1])
                else:
                    negtag = 'NONEG'
                annotatedTags.append(tagword + '##NEGAT:' + negtag + '##POS:' + str(posval) + '##NEG:' + str(negval))
            else:
                annotatedTags.append(tagword)

        # Completed scan - execute final score adjustments
        (resultpos, resultneg) = self._doc_score_adjust(postotal, negtotal)

        # updates class data structures containing results
        self.resultdata = {
            'annotated_doc': ' '.join(annotatedTags),
            'doc': Doc,
            'resultpos': resultpos,
            'resultneg': resultneg,
            'tokens_found': foundcounter,
            'tokens_negated': sum(self.vNEG),
            'found_list': self.tag_counter,
            'unscored_list': tagUnscored
        }

        self._debug('Result data: %s'%str(self.resultdata))
        return (resultpos, resultneg)


    def set_parameters(self, **kwargs):
        '''
          Parameters that can be set on this type of algorithm:
          L, lexicon
          a,n,v,r: POS tags to enable
          negation: True/False for negation detection
          negation_window: tokens to consider in negated window
          score_function: score adjustment function (looks for self._score_<score_function>)
          score_mode: score each word once/always
          score_freq: frequency adjust word scores
          score_stop: discard stop words
        '''
        # calls superclass set_parameters
        if 'L' in kwargs.keys():
            self.set_lexicon(kwargs['L'])

        # POS tags to enable
        tags = {'a': self.a, 'n': self.n, 'v': self.v, 'r': self.r}
        for tag in tags.keys():
            if tag in kwargs.keys():
                tags[tag] = kwargs[tag]
        self.set_active_pos(a=tags['a'], v=tags['v'], n=tags['n'], r=tags['r'])

        # Negation
        if 'negation' in kwargs.keys():
            window = 0
            adj = 0.0
            if 'negation_window' in kwargs.keys(): window = kwargs['negation_window']
            if 'negation_adjustment' in kwargs.keys(): adj = kwargs['negation_adjustment']
            self.set_neg_detection(kwargs['negation'], window, adj)

        #TODO: this needs stronger validation
        if kwargs.has_key('score_mode'): self.score_mode = kwargs['score_mode']
        if kwargs.has_key('score_freq'): self.score_freq = kwargs['score_freq']
        if kwargs.has_key('score_stop'): self.score_stop = kwargs['score_stop']

        if kwargs.has_key('score_function'):
            try:
                self.score_function = getattr(self, '_score_'+kwargs['score_function'])
            except Exception:
                self.score_function = self._score_noop

    #
    # score weight adjustment functions
    #
    def _score_noop(self, score, i, N):
        '''
          no-op function: returns score given as-is
        '''
        return score

    def _score_linear(self, score, i, N):
        '''
         lineasr adjustment of scores per word position in text
        '''
        # we want the interval to vary from 0.5-1.0 of original score
        BAND=0.5
        FLOOR=0.5
        if N==0: 
            return score
        else:
            return score*(((float(i)/float(N))*BAND)+FLOOR)

    def _score_cosine(self, score, i, N):
        '''
         cosine adjustment gives a heavier weight to scores at the start and end of document
        '''
        if N==0: return score
        BAND=0.5
        # normalize word position
        norm_i = float(i)/float(N)
        # get cosine function, ranging from 0.5-1.0
        cos_val = BAND+((math.cos(20.0*norm_i/math.pi)+1.0)/4.0)
        return score*cos_val


#
# Sample Pre-defined algorithms based on BasicDocSentiScore
#
class AV_AllWordsDocSentiScore(BasicDocSentiScore):
    '''
     Pre-configured BasicDocSentiScore to score all words, negation detection enabled, A,V POS tags
    '''
    def __init__(self, Lex):
        super(AV_AllWordsDocSentiScore, self).__init__()
        self.set_parameters(L=Lex, a=True, v=True, n=False, r=False, 
                            negation=True, negation_window=5,
                            score_mode=self.SCOREALL, score_stop=True, score_freq=True)


class A_AllWordsDocSentiScore(BasicDocSentiScore):
    '''
     Pre-configured BasicDocSentiScore to score all words, negation detection enabled, A POS tag
    '''
    def __init__(self, Lex):
        super(A_AllWordsDocSentiScore, self).__init__()
        self.set_parameters(L=Lex, a=True, v=False, n=False, r=False, 
                            negation=True, negation_window=5,
                            score_mode=self.SCOREALL, score_stop=True, score_freq=True)

class A_OnceWordsDocSentiScore(BasicDocSentiScore):
    '''
     Pre-configured BasicDocSentiScore to score once, negation detection enabled, A POS tags
    '''
    def __init__(self, Lex):
        super(A_OnceWordsDocSentiScore, self).__init__()
        self.set_parameters(L=Lex, a=True, v=False, n=False, r=False, 
                            negation=True, negation_window=5,
                            score_mode=self.SCOREONCE, score_stop=True, score_freq=True)

class AV_OnceWordsDocSentiScore(BasicDocSentiScore):
    '''
     Pre-configured BasicDocSentiScore to score once, negation detection enabled, A,V POS tags
    '''
    def __init__(self, Lex):
        super(AV_OnceWordsDocSentiScore, self).__init__()
        self.set_parameters(L=Lex, a=True, v=True, n=False, r=False, 
                            negation=True, negation_window=5,
                            score_mode=self.SCOREONCE, score_stop=True, score_freq=True)

class AV_Lin_AllWordsDocSentiScore(BasicDocSentiScore):
    '''
     Pre-configured BasicDocSentiScore to score once, negation detection enabled, A,V POS tags
    '''
    def __init__(self, Lex):
        super(AV_Lin_AllWordsDocSentiScore, self).__init__()
        self.set_parameters(L=Lex, a=True, v=True, n=False, r=False, 
                            negation=True, negation_window=5,
                            score_mode=self.SCOREALL, score_stop=True, score_freq=True,
                            score_function='linear')

class A_Lin_AllWordsDocSentiScore(BasicDocSentiScore):
    '''
     Pre-configured BasicDocSentiScore to score once, negation detection enabled, A,V POS tags
    '''
    def __init__(self, Lex):
        super(A_Lin_AllWordsDocSentiScore, self).__init__()
        self.set_parameters(L=Lex, a=True, v=False, n=False, r=False, 
                            negation=True, negation_window=5,
                            score_mode=self.SCOREALL, score_stop=True, score_freq=True,
                            score_function='linear')

class A_Cos_AllWordsDocSentiScore(BasicDocSentiScore):
    '''
     Pre-configured BasicDocSentiScore to score once, negation detection enabled, A,V POS tags
    '''
    def __init__(self, Lex):
        super(A_Cos_AllWordsDocSentiScore, self).__init__()
        self.set_parameters(L=Lex, a=True, v=False, n=False, r=False, 
                            negation=True, negation_window=5,
                            score_mode=self.SCOREALL, score_stop=True, score_freq=True,
                            score_function='cosine')

class AV_Cos_AllWordsDocSentiScore(BasicDocSentiScore):
    '''
     Pre-configured BasicDocSentiScore to score once, negation detection enabled, A,V POS tags
    '''
    def __init__(self, Lex):
        super(AV_Cos_AllWordsDocSentiScore, self).__init__()
        self.set_parameters(L=Lex, a=True, v=True, n=False, r=False, 
                            negation=True, negation_window=5,
                            score_mode=self.SCOREALL, score_stop=True, score_freq=True,
                            score_function='cosine')
