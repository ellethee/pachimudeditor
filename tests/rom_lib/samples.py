"""Aree di esempio scritte a mano (formato basedmud/ROM) per i test."""

OLD_HEADER = """#AREA
test.are~
Test Area~
{ 1 10} Luca  Test Area~
100 199

"""

MOBILES = """#MOBILES
#100
wizard oldname~
the wizard~
A wizard walks around.
~
The wizard looks old.
~
human~
ABV D 900 0
23 2 1d1+999 1d1+999 1d8+32 magic
-15 -15 -15 -15
AF ABCD 0 0
stand stand male 15000
0 0 medium 0
F act A
F vul B
M act_prog 101 hello~
#101
rat~
a rat~
A rat scurries.
~
A rat.
~
rodent~
0 0 0 0
1 0 1d2+1 1d1+0 1d2+0 bite
0 0 0 0
0 0 0 0
stand stand none 0
0 0 tiny 0
#0

"""

OBJECTS = """#OBJECTS
#100
sword blade~
a long sword~
A long sword lies here.~
steel~
weapon BI AN
sword 4 10 slash EF
20 100 500 P
A
18 3
F
A 12 -2 F
E
sword~
Fine steel.
~
#101
bottle~
a bottle~
A bottle is here.~
glass~
drink 0 A
16 16 'local specialty' 0 0
0 10 5 G
#102
bag~
a bag~
A bag.~
cloth~
container 0 A
50 AB 0 100 100
0 10 5 P
#103
potion~
a potion~
A potion.~
glass~
potion 0 A
10 'sanctuary' 'cure light' '' ''
0 1 1 P
#104
torch~
a torch~
A torch.~
wood~
light 0 A
0 0 100 0 0
0 1 1 P
#0

"""

ROOMS = """#ROOMS
#100
The Hall~
A big hall.
Second line.
~
0 CDS 1
D0
North is dark.
~
door~
1 101 101
D2
~
~
0 -1 101
E
plaque~
A plaque.
~
O Luca~
M 120 H 130
C mystic~
S
#101
Closet~
A closet.
~
0 0 0
S
#0

"""

RESETS = """#RESETS
D 0 100 0 2
M 0 100 1 100 1	* the wizard
E 1 100 -1 16
G 1 101 -1
O 0 102 1 100
P 0 103 1 102 1
R 0 100 2
* una nota
S

"""

SHOPS = """#SHOPS
100  2  3  4 10  0 	 105  15 	 0 23 	* the wizard
0

"""

SPECIALS = """#SPECIALS
M 100 spec_cast_mage  	* the wizard
* nota
S

"""

MOBPROGS = """#MOBPROGS
#101
say Hello there
mob echo hi
~
#0

"""

HELPS = """#HELPS
0 TEST HELP~
This is help text.
~

-1 LEVEL~
Immortal help.
~

0 $~

"""

SOCIALS = """#SOCIALS

gack
Gaaack!
$n gacks with dismay!
Appalled, you gack at $N.
$n gacks expressively.
$n gacks, and looks your way.
That person isn't here.
*GACK!*
Appalled, $n gacks at $mself!

kiss 0 0
Isn't there someone?
$
You kiss $M.
$n kisses $N.
$n kisses you.
Never around.
#

#0
"""

AREADATA = """#AREADATA
Name Test Area~
Builders Luca~
VNUMs 100 199
Credits Luca Test~
Security 5
End

"""

FULL = OLD_HEADER + MOBILES + OBJECTS + ROOMS + RESETS + SHOPS + SPECIALS + MOBPROGS + HELPS + SOCIALS + "#$\n"

FULL_DATA = AREADATA + MOBILES + OBJECTS + ROOMS + RESETS + SHOPS + SPECIALS + MOBPROGS + "#$\n"
