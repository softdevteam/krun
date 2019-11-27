#!/usr/bin/awk -f
BEGIN             {C=0; O=0; E=0; keys=0}
/^keys/         {keys=1}
keys == 1 && $1 =="C"    {C++}
keys == 1 && $1 =="E"    {E++}
keys == 1 && $1 =="O"    {O++}
END            {print "C=" C "  O=" O "  E=" E "   " (C+E) / (C + O + E) * 100 "%"}
