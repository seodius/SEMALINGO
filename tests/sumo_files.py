"""Small SUMO and CILI files in the real formats."""

MERGE_KIF = '''; ; The SUMO is freely available, subject to the following IEEE license.
(subclass Organ AnimalAnatomicalStructure)
(subclass Eye Organ)
(documentation Eye EnglishWrittenLanguage "The &%Organ of sight; see \\"Seeing\\".")
(termFormat EnglishLanguage Eye "eye")
(subclass Seeing Perception)
(subclass Looking Seeing)
(subclass Looking IntentionalProcess)
(instance Sun Star)
(subrelation part located)
(subAttribute Blind Disabled)
(relatedInternalConcept Seeing Looking)
(partition Organ Eye Ear)
(capability Seeing agent Eye)
(=>
  (instance ?X Eye)
  (subclass ?Y Organ))
; (subclass Nut PlantAgriculturalProduct)
(documentation Legume EnglishWrittenLanguage "Plants in the pea or bean family, Fabaceae.")
(subclass Legume FruitOrVegetable)
'''

WORDNET_NOUN = '''  1 This software and database is being provided to you, the LICENSEE, by
  2 Princeton University under the following license.
05311054 08 n 03 eye 0 oculus 0 optic 0 000 | the organ of sight &%Eye=
13136556 20 n 01 nut 0 000 | usually large hard-shelled seed &%Nut=
00002137 03 n 01 abstraction 0 000 | a general concept formed by extracting common features &%Abstract+
09450163 17 n 01 sun 0 000 | the star that is the source of light and heat for the planets &%Sun@
05661902 09 n 01 cover 0 000 | a false identity and background &%Disseminating[
'''

CILI_MAP = "i64868\t05311054-n\ni105680\t13136556-n\ni1\t00001740-a\n"
