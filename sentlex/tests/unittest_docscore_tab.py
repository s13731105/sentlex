try:
    import sentlex.sentanalysis_taboada as sentdoc
except Exception:
    import sentanalysis_taboada as sentdoc

try:
    import sentlex.sentlex as sentlex
except Exception:
    import sentlex as sentlex

import sys,os
import unittest

#####
#
# Unit Testing for doc sentiment analysis
#
####

#
# Data
#
TESTDOC_ADJ = 'good/JJ good/JJ good/JJ good/JJ good/JJ good/JJ good/JJ good/JJ good/JJ good/JJ' 
TESTDOC_UNTAGGED = 'this cookie is good. it is very good indeed'
TESTDOC_BADADJ = 'bad_JJ Bad_JJ bAd_JJ'
TESTDOC_NEGATED = 'not/DT bad/JJ movie/NN ./. blah/NN blah/NN not/DT really/RR good/JJ either/DT ./.'
TESTDOC_CORRUPT = 'this_DT doc_NN is_VB not_DT not_DT not_DT in great/JJ shape/JJ good_JJ good_JJ good_JJ'
TESTDOC_EMPTY = ''

# T0 - Basic Class functionality
class T0_parameter_setting(unittest.TestCase):
    def runTest(self):
        # empty list
        ds = sentdoc.TaboadaDocSentiScore()
        ds.verbose=True

        ds.set_active_pos(True, False, False, False)
        ds.set_parameters(negation_shift=0.5, negation=True, negation_window=15)

        self.assertEqual((ds.a, ds.v, ds.n, ds.r), (True, False, False, False), 'Failed set POS parameters')
        self.assertEqual((ds.negation, ds.negation_window), (True, 15), 'Failed set negation')
        self.assertEqual(ds.score_mode, ds.BACKOFF, 'Backoff parameter is not correctly set')


class T1_scoring_documents(unittest.TestCase):
    def runTest(self):
        # load lexicon
        L = sentlex.MobyLexicon()
        self.assertTrue(L.is_loaded, 'Test lexicon did not load correctly')

        # create a class that scores only adjectives
        ds = sentdoc.TaboadaDocSentiScore()
        ds.verbose=True
        ds.set_active_pos(True, False, False, False)
        ds.set_parameters(score_freq=False, negation=True, negation_shift=0.5)
        ds.set_lexicon(L)

        # separator ok?
        self.assertEqual(ds._detect_tag(TESTDOC_ADJ), '/', 'Unable to detect correct separator')

        # now score!
        (dpos, dneg) = ds.classify_document(TESTDOC_ADJ, verbose=True)
        self.assertTrue(ds.resultdata and ds.resultdata.has_key('doc') and ds.resultdata.has_key('annotated_doc')\
            and ds.resultdata.has_key('resultpos') and ds.resultdata.has_key('resultneg'), 'Did not populate resultdata after scoring doc')

        self.assertTrue(dpos > 0.0, 'Did not find positive words on positive doc')
        print 'TESTDOC_ADJ (pos,neg): %2.2f %2.2f' % (dpos, dneg)

        # again, for negative text
        (dpos, dneg) = ds.classify_document(TESTDOC_BADADJ, verbose=True)
        self.assertTrue(dneg > 0.0, 'Did not find negative words on negative doc')
        print 'TESTDOC_BADADJ (pos,neg): %2.2f %2.2f' % (dpos, dneg)

        # negated text
        ds.set_neg_detection(True, 5)
        (dpos, dneg) = ds.classify_document(TESTDOC_NEGATED, verbose=True)
        print 'TESTDOC_NEGATED (pos,neg): %2.2f %2.2f' % (dpos, dneg)

        # currupt data - should still work
        (dpos, dneg) = ds.classify_document(TESTDOC_CORRUPT, verbose=True)
        self.assertTrue(dpos > dneg, 'Did not process corrupt document correctly')


class T4_sample_classes(unittest.TestCase):
    def runTest(self):
        # load lexicon
        L = sentlex.MobyLexicon()
        self.assertTrue(L.is_loaded, 'Test lexicon did not load correctly')
        print '=== Testing all sample algorithms==='
        for algo in [ sentdoc.AV_LightTabSentiScore(L), 
                      sentdoc.AV_AggressiveTabSentiScore(L),
                    ]:
            algo.verbose=True
            print ' ==> ' + str(algo.__class__)
            (p,n) = algo.classify_document(TESTDOC_NEGATED, verbose=True)

#
# Runs unit testing if module is called directly
#
if __name__ == "__main__":
    
   # Run those guys
   unittest.main()
