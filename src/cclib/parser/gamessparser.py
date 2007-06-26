"""
cclib (http://cclib.sf.net) is (c) 2006, the cclib development team
and licensed under the LGPL (http://www.gnu.org/copyleft/lgpl.html).
"""

__revision__ = "$Revision$"


import re

# If numpy is not installed, try to import Numeric instead.
try:
    import numpy
except ImportError:
    import Numeric as numpy

import utils
import logfileparser


class GAMESS(logfileparser.Logfile):
    """A GAMESS log file."""
    SCFRMS, SCFMAX, SCFENERGY = range(3) # Used to index self.scftargets[]
    def __init__(self, *args):

        # Call the __init__ method of the superclass
        super(GAMESS, self).__init__(logname="GAMESS", *args)

    def __str__(self):
        """Return a string representation of the object."""
        return "GAMESS log file %s" % (self.filename)

    def __repr__(self):
        """Return a representation of the object."""
        return 'GAMESS("%s")' % (self.filename)

    def normalisesym(self, label):
        """Normalise the symmetries used by GAMESS.

        To normalise, two rules need to be applied:
        (1) Occurences of U/G in the 2/3 position of the label
            must be lower-cased
        (2) Two single quotation marks must be replaced by a double

        >>> t = GAMESS("dummyfile").normalisesym
        >>> labels = ['A', 'A1', 'A1G', "A'", "A''", "AG"]
        >>> answers = map(t, labels)
        >>> print answers
        ['A', 'A1', 'A1g', "A'", 'A"', 'Ag']
        """
        if label[1:] == "''":
            end = '"'
        else:
            end = label[1:].replace("U", "u").replace("G", "g")
        return label[0] + end

    def before_parsing(self):

        self.firststdorient = True # Used to decide whether to wipe the atomcoords clean
        self.geooptfinished = False # Used to avoid extracting the final geometry twice
        self.cihamtyp = "none" # Type of CI Hamiltonian: saps or dets.
    
    def extract(self, inputfile, line):
        """Extract information from the file object inputfile."""
        
        if line.find("OPTTOL") >= 0:
            # Two possibilities:
            #           OPTTOL = 1.000E-04          RMIN   = 1.500E-03
            # INPUT CARD> $STATPT OPTTOL=0.0001 NSTEP=100 $END
            if not hasattr(self, "geotargets"):
                temp = line.split()
                for i, x in enumerate(temp):
                    if x.find("OPTTOL") >= 0:
                        if x == "OPTTOL":
                            opttol = float(temp[i + 2])
                        else:
                            opttol = float(x.split('=')[1])
                        self.geotargets = numpy.array([opttol, 3. / opttol], "d")
                        
        if line.find("FINAL") == 1:
            if not hasattr(self, "scfenergies"):
                self.scfenergies = []
        # Has to deal with such lines as:
        #  FINAL R-B3LYP ENERGY IS     -382.0507446475 AFTER  10 ITERATIONS
        #  FINAL ENERGY IS     -379.7594673378 AFTER   9 ITERATIONS
        # ...so take the number after the "IS"
            temp = line.split()
            self.scfenergies.append(utils.convertor(float(temp[temp.index("IS") + 1]), "hartree", "eV"))

        # Total energies after Moller-Plesset corrections
        if line.find("RESULTS OF MOLLER-PLESSET") >= 0:
            # Output looks something like this:
            # RESULTS OF MOLLER-PLESSET 2ND ORDER CORRECTION ARE
            #         E(0)=      -285.7568061536
            #         E(1)=         0.0
            #         E(2)=        -0.9679419329
            #       E(MP2)=      -286.7247480864
            # where E(MP2) = E(0) + E(2)
            if not hasattr(self, "mpenergies"):
                self.mpenergies = []
            # Each iteration has a new print-out
            self.mpenergies.append([])
            # GAMESS-US presently supports only second order corrections (MP2)
            # PC GAMESS also has higher levels (3rd and 4th), with different output
            # Only the highest level MP4 energy is gathered (SDQ or SDTQ)
            mplevel = int(line[27:28])
            while line.strip() <> "..... DONE WITH MP%i ENERGY ....." %mplevel:
                line = inputfile.next()
                if len(line.split()) > 0:
                    # Only up to MP2 correction
                    if line.split()[0] == "E(MP2)=":
                        mp2energy = float(line.split()[1])
                        self.mpenergies[-1].append(utils.convertor(mp2energy, "hartree", "eV"))
                    # MP2 before higher order calculations
                    if line.split()[0] == "E(MP2)":
                        mp2energy = float(line.split()[2])
                        self.mpenergies[-1].append(utils.convertor(mp2energy, "hartree", "eV"))
                    if line.split()[0] == "E(MP3)":
                        mp3energy = float(line.split()[2])
                        self.mpenergies[-1].append(utils.convertor(mp3energy, "hartree", "eV"))
                    if line.split()[0] in ["E(MP4-SDQ)", "E(MP4-SDTQ)"]:
                        mp4energy = float(line.split()[2])
                        self.mpenergies[-1].append(utils.convertor(mp4energy, "hartree", "eV"))

        # Total energies after Coupled Cluster calculations
        # Only the highest Coupled Cluster level result is gathered
        if line[12:23] == "CCD ENERGY:":
            if not hasattr(self, "ccenergies"):
                self.ccenergies = []
            ccenergy = float(line.split()[2])
            self.ccenergies.append(utils.convertor(ccenergy, "hartree", "eV"))
        if line[8:23] == "CCSD    ENERGY:":
            if not hasattr(self, "ccenergies"):
                self.ccenergies = []
            ccenergy = float(line.split()[2])
            line = inputfile.next()
            if line[8:23] == "CCSD[T] ENERGY:":
                ccenergy = float(line.split()[2])
                line = inputfile.next()
                if line[8:23] == "CCSD(T) ENERGY:":
                    ccenergy = float(line.split()[2])
            self.ccenergies.append(utils.convertor(ccenergy, "hartree", "eV"))
        # Also collect MP2 energies, which are always calculated before CC
        if line [8:23] == "MBPT(2) ENERGY:":
            if not hasattr(self, "mpenergies"):
                self.mpenergies = []
            self.mpenergies.append([])
            mp2energy = float(line.split()[2])
            self.mpenergies[-1].append(utils.convertor(mp2energy, "hartree", "eV"))

        # Extract charge and multiplicity
        if line[1:19] == "CHARGE OF MOLECULE":
            self.charge = int(line.split()[-1])
            self.mult = int(inputfile.next().split()[-1])

        # etenergies (used only for CIS runs now)
        if "EXCITATION ENERGIES" in line:
            if not hasattr(self, "etenergies"):
                self.etenergies = []
            header = inputfile.next()
            dashes = inputfile.next()
            line = inputfile.next()
            while len(line.split()) > 0:
                # Take hartree value with more numbers, and convert.
                # Note that the values listed after this are also less exact!
                etenergy = float(line.split()[1])
                self.etenergies.append(utils.convertor(etenergy, "hartree", "cm-1"))
                line = inputfile.next()

        # Detect the CI hamiltonian type, if applicable.
        # Should always be detected if CIS is done.
        if line[8:64] == "RESULTS FROM SPIN-ADAPTED ANTISYMMETRIZED PRODUCT (SAPS)":
            self.cihamtyp = "saps"
        if line[8:64] == "RESULTS FROM DETERMINANT BASED ATOMIC ORBITAL CI-SINGLES":
            self.cihamtyp = "dets"

        # etsecs (used only for CIS runs for now)
        if line[1:14] == "EXCITED STATE":
            if not hasattr(self, 'etsecs'):
                self.etsecs = []
            if not hasattr(self, 'etsyms'):
                self.etsyms = []
            statenumber = int(line.split()[2])
            spin = int(float(line.split()[7]))
            if spin == 0:
                sym = "Singlet"
            if spin == 1:
                sym = "Triplet"
            sym += '-' + line.split()[-1]
            self.etsyms.append(sym)
            # skip 5 lines
            for i in range(5):
                line = inputfile.next()
            line = inputfile.next()
            CIScontribs = []
            while line.strip()[0] != "-":
                MOtype = 0
                # alpha/beta are specified for hamtyp=dets
                if self.cihamtyp == "dets":
                    if line.split()[0] == "BETA":
                        MOtype = 1
                fromMO = int(line.split()[-3])-1
                toMO = int(line.split()[-2])-1
                coeff = float(line.split()[-1])
                # With the SAPS hamiltonian, the coefficients are multiplied
                #   by sqrt(2) so that they normalize to 1.
                # With DETS, both alpha and beta excitations are printed.
                if self.cihamtyp == "saps":
                    coeff /= numpy.sqrt(2.0)
                CIScontribs.append([(fromMO,MOtype),(toMO,MOtype),coeff])
                line = inputfile.next()
            self.etsecs.append(CIScontribs)
            
        # etoscs (used only for CIS runs now)
        if line[1:50] == "TRANSITION FROM THE GROUND STATE TO EXCITED STATE":
            if not hasattr(self, "etoscs"):
                self.etoscs = []
            statenumber = int(line.split()[-1])
            # skip 7 lines
            for i in range(8):
                line = inputfile.next()
            strength = float(line.split()[3])
            self.etoscs.append(strength)

        if line.find("MAXIMUM GRADIENT") > 0:
            if not hasattr(self, "geovalues"):
                self.geovalues = []
            temp = line.strip().split()
            self.geovalues.append([float(temp[3]), float(temp[7])])

        if line[11:50] == "ATOMIC                      COORDINATES":
            # This is the input orientation, which is the only data available for
            # SP calcs, but which should be overwritten by the standard orientation
            # values, which is the only information available for all geoopt cycles.
            if not hasattr(self, "atomcoords"):
                self.atomcoords = []
                self.atomnos = []
            line = inputfile.next()
            atomcoords = []
            atomnos = []
            line = inputfile.next()
            while line.strip():
                temp = line.strip().split()
                atomcoords.append([utils.convertor(float(x), "bohr", "Angstrom") for x in temp[2:5]])
                atomnos.append(int(round(float(temp[1])))) # Don't use the atom name as this is arbitary
                line = inputfile.next()
            self.atomnos = numpy.array(atomnos, "i")
            self.atomcoords.append(atomcoords)

        if line[12:40] == "EQUILIBRIUM GEOMETRY LOCATED":
            # Prevent extraction of the final geometry twice
            self.geooptfinished = True
        
        if line[1:29] == "COORDINATES OF ALL ATOMS ARE" and not self.geooptfinished:
            # This is the standard orientation, which is the only coordinate
            # information available for all geometry optimisation cycles.
            # The input orientation will be overwritten if this is a geometry optimisation
            # We assume that a previous Input Orientation has been found and
            # used to extract the atomnos
            if self.firststdorient:
                self.firststdorient = False
                # Wipes out the single input coordinate at the start of the file
                self.atomcoords = []
                
            line = inputfile.next()
            hyphens = inputfile.next()

            atomcoords = []
            line = inputfile.next()                
            while line.strip():
                temp = line.strip().split()
                atomcoords.append(map(float, temp[2:5]))
                line = inputfile.next()
            self.atomcoords.append(atomcoords)
        
        if line.rstrip()[-15:] == "SCF CALCULATION":
            # This is the section with the SCF information
            line = inputfile.next()
            while line.find("ITER EX") < 0:
                if line.find("DENSITY CONV=") >= 0 or line.find("DENSITY MATRIX CONV=") >= 0:
        # Needs to deal with lines like:
        # (GAMESS VERSION = 12 DEC 2003)
        #     DENSITY MATRIX CONV=  2.00E-05  DFT GRID SWITCH THRESHOLD=  3.00E-04
        # (GAMESS VERSION = 22 FEB 2006)
        #           DENSITY MATRIX CONV=  1.00E-05
        # (PC GAMESS version 6.2, Not DFT?)
        #     DENSITY CONV=  1.00E-05
                    index = line.find("DENSITY CONV=")
                    if index < 0:
                        index = line.find("DENSITY MATRIX CONV=")
                        index += len("DENSITY MATRIX CONV=")
                    else:
                        index += len("DENSITY CONV=")
                    scftarget = float(line[index:].split()[0])
                line = inputfile.next()

            if not hasattr(self, "scftargets"):
                self.scftargets = []
            self.scftargets.append([scftarget])

            if not hasattr(self,"scfvalues"):
                self.scfvalues = []
            line = inputfile.next()
            values = []
            while line.strip():
            # The SCF information is terminated by a blank line                    
                try:
                    temp = int(line[0:4])
                except ValueError:
            # Occurs for:
            #  * * *   INITIATING DIIS PROCEDURE   * * *
            #  CONVERGED TO SWOFF, SO DFT CALCULATION IS NOW SWITCHED ON
            #  DFT CODE IS SWITCHING BACK TO THE FINER GRID
                    pass
                else:
                    values.append([float(line.split()[5])])
                line = inputfile.next()
            self.scfvalues.append(values)

        if line.find("NORMAL COORDINATE ANALYSIS IN THE HARMONIC APPROXIMATION") >= 0:
        # GAMESS has...
        # MODES 1 TO 6 ARE TAKEN AS ROTATIONS AND TRANSLATIONS.
        #
        #     FREQUENCIES IN CM**-1, IR INTENSITIES IN DEBYE**2/AMU-ANGSTROM**2,
        #     REDUCED MASSES IN AMU.
        #
        #                          1           2           3           4           5
        #       FREQUENCY:        52.49       41.45       17.61        9.23       10.61  
        #    REDUCED MASS:      3.92418     3.77048     5.43419     6.44636     5.50693
        #    IR INTENSITY:      0.00013     0.00001     0.00004     0.00000     0.00003
        
        # whereas PC-GAMESS has...
        # MODES 1 TO 6 ARE TAKEN AS ROTATIONS AND TRANSLATIONS.
        #
        #     FREQUENCIES IN CM**-1, IR INTENSITIES IN DEBYE**2/AMU-ANGSTROM**2
        #
        #                          1           2           3           4           5
        #       FREQUENCY:         5.89        1.46        0.01        0.01        0.01  
        #    IR INTENSITY:      0.00000     0.00000     0.00000     0.00000     0.00000
        
        # If Raman is present we have (for PC-GAMESS)...
        # MODES 1 TO 6 ARE TAKEN AS ROTATIONS AND TRANSLATIONS.
        #
        #     FREQUENCIES IN CM**-1, IR INTENSITIES IN DEBYE**2/AMU-ANGSTROM**2
        #     RAMAN INTENSITIES IN ANGSTROM**4/AMU, DEPOLARIZATIONS ARE DIMENSIONLESS
        #
        #                          1           2           3           4           5
        #       FREQUENCY:         5.89        1.46        0.04        0.03        0.01  
        #    IR INTENSITY:      0.00000     0.00000     0.00000     0.00000     0.00000
        # RAMAN INTENSITY:       12.675       1.828       0.000       0.000       0.000
        #  DEPOLARIZATION:        0.750       0.750       0.124       0.009       0.750

        # If PC-GAMESS has not reached the stationary point we have
        # MODES 1 TO 5 ARE TAKEN AS ROTATIONS AND TRANSLATIONS.
        #
        #     FREQUENCIES IN CM**-1, IR INTENSITIES IN DEBYE**2/AMU-ANGSTROM**2
        #
        #     *******************************************************
        #     * THIS IS NOT A STATIONARY POINT ON THE MOLECULAR PES *
        #     *     THE VIBRATIONAL ANALYSIS IS NOT VALID !!!       *
        #     *******************************************************
        #
        #                          1           2           3           4           5
        
        # MODES 2 TO 7 ARE TAKEN AS ROTATIONS AND TRANSLATIONS.

            self.vibfreqs = []
            self.vibirs = []
            self.vibdisps = []

            # Need to get to the modes line
            warning = False
            while line.find("MODES") == -1:
                line = inputfile.next()
                if line.find("THIS IS NOT A STATIONARY POINT")>=0:
                    warning = True
            startrot = int(line.split()[1])
            endrot = int(line.split()[3])
            blank = inputfile.next()

            line = inputfile.next() # FREQUENCIES, etc.
            while line != blank:
                line = inputfile.next()
            if warning: # Get past the second warning
                line = inputfile.next()
                while line!= blank:
                    line = inputfile.next()
                self.logger.warning("This is not a stationary point on the molecular"
                                    "PES. The vibrational analysis is not valid.")
            
            freqNo = inputfile.next()
            while freqNo.find("SAYVETZ") == -1:
                freq = inputfile.next().strip().split()[1:]
            # May include imaginary frequencies
            #       FREQUENCY:       825.18 I    111.53       12.62       10.70        0.89
                newfreq = []
                for i, x in enumerate(freq):
                    if x!="I":
                        newfreq.append(float(x))
                    else:
                        newfreq[-1] = -newfreq[-1]
                self.vibfreqs.extend(newfreq)
                line = inputfile.next()
                if line.find("REDUCED") >= 0: # skip the reduced mass (not always present)
                    line = inputfile.next()
                irIntensity = map(float, line.strip().split()[2:])
                self.vibirs.extend([utils.convertor(x, "Debye^2/amu-Angstrom^2", "km/mol") for x in irIntensity])
                line = inputfile.next()
                if line.find("RAMAN") >= 0:
                    if not hasattr(self,"vibramans"):
                        self.vibramans = []
                    ramanIntensity = line.strip().split()
                    self.vibramans.extend(map(float, ramanIntensity[2:]))
                    depolar = inputfile.next()
                    line = inputfile.next()
                assert line == blank

                # Extract the Cartesian displacement vectors
                p = [ [], [], [], [], [] ]
                for j in range(len(self.atomnos)):
                    q = [ [], [], [], [], [] ]
                    for k in range(3): # x, y, z
                        line = inputfile.next()[21:]
                        broken = map(float, line.split())
                        for l in range(len(broken)):
                            q[l].append(broken[l])
                    for k in range(len(broken)):
                        p[k].append(q[k])
                self.vibdisps.extend(p[:len(broken)])

                # Skip the Sayvetz stuff at the end
                for j in range(10):
                    line = inputfile.next()
                blank = inputfile.next()
                freqNo = inputfile.next()
            # Exclude rotations and translations
            self.vibfreqs = numpy.array(self.vibfreqs[:startrot-1]+self.vibfreqs[endrot:], "d")
            self.vibirs = numpy.array(self.vibirs[:startrot-1]+self.vibirs[endrot:], "d")
            self.vibdisps = numpy.array(self.vibdisps[:startrot-1]+self.vibdisps[endrot:], "d")
            if hasattr(self, "vibramans"):
                self.vibramans = numpy.array(self.vibramans[:startrot-1]+self.vibramans[endrot:], "d")

        if line[5:21] == "ATOMIC BASIS SET":
            self.gbasis = []
            line = inputfile.next()
            while line.find("SHELL")<0:
                line = inputfile.next()
            blank = inputfile.next()
            atomname = inputfile.next()
            # shellcounter stores the shell no of the last shell
            # in the previous set of primitives
            shellcounter = 1
            while line.find("TOTAL NUMBER")<0:
                blank = inputfile.next()
                line = inputfile.next()
                shellno = int(line.split()[0])
                shellgap = shellno - shellcounter
                gbasis = [] # Stores basis sets on one atom
                shellsize = 0
                while len(line.split())!=1 and line.find("TOTAL NUMBER")<0:
                    shellsize += 1
                    coeff = {}
                    # coefficients and symmetries for a block of rows
                    while line.strip():
                        temp = line.strip().split()
                        sym = temp[1]
                        assert sym in ['S', 'P', 'D', 'F', 'G', 'L']
                        if sym == "L": # L refers to SP
                            if len(temp)==6: # GAMESS US
                                coeff.setdefault("S", []).append( (float(temp[3]), float(temp[4])) )
                                coeff.setdefault("P", []).append( (float(temp[3]), float(temp[5])) )
                            else: # PC GAMESS
                                assert temp[6][-1] == temp[9][-1] == ')'
                                coeff.setdefault("S", []).append( (float(temp[3]), float(temp[6][:-1])) )
                                coeff.setdefault("P", []).append( (float(temp[3]), float(temp[9][:-1])) )
                        else:
                            if len(temp)==5: # GAMESS US
                                coeff.setdefault(sym, []).append( (float(temp[3]), float(temp[4])) )
                            else: # PC GAMESS
                                assert temp[6][-1] == ')'
                                coeff.setdefault(sym, []).append( (float(temp[3]), float(temp[6][:-1])) )
                        line = inputfile.next()
                    # either a blank or a continuation of the block
                    if sym == "L":
                        gbasis.append( ('S', coeff['S']))
                        gbasis.append( ('P', coeff['P']))
                    else:
                        gbasis.append( (sym, coeff[sym]))
                    line = inputfile.next()
                # either the start of the next block or the start of a new atom or
                # the end of the basis function section
                
                numtoadd = 1 + (shellgap / shellsize)
                shellcounter = shellno + shellsize
                for x in range(numtoadd):
                    self.gbasis.append(gbasis)

        if line.find("EIGENVECTORS") == 10 or line.find("MOLECULAR OBRITALS") == 10:
            # The details returned come from the *final* report of evalues and
            #   the last list of symmetries in the log file.
            # Should be followed by lines like this:
            #           ------------
            #           EIGENVECTORS
            #           ------------
            # 
            #                       1          2          3          4          5
            #                   -10.0162   -10.0161   -10.0039   -10.0039   -10.0029
            #                      BU         AG         BU         AG         AG  
            #     1  C  1  S    0.699293   0.699290  -0.027566   0.027799   0.002412
            #     2  C  1  S    0.031569   0.031361   0.004097  -0.004054  -0.000605
            #     3  C  1  X    0.000908   0.000632  -0.004163   0.004132   0.000619
            #     4  C  1  Y   -0.000019   0.000033   0.000668  -0.000651   0.005256
            #     5  C  1  Z    0.000000   0.000000   0.000000   0.000000   0.000000
            #     6  C  2  S   -0.699293   0.699290   0.027566   0.027799   0.002412
            #     7  C  2  S   -0.031569   0.031361  -0.004097  -0.004054  -0.000605
            #     8  C  2  X    0.000908  -0.000632  -0.004163  -0.004132  -0.000619
            #     9  C  2  Y   -0.000019  -0.000033   0.000668   0.000651  -0.005256
            #    10  C  2  Z    0.000000   0.000000   0.000000   0.000000   0.000000
            #    11  C  3  S   -0.018967  -0.019439   0.011799  -0.014884  -0.452328
            #    12  C  3  S   -0.007748  -0.006932   0.000680  -0.000695  -0.024917
            #    13  C  3  X    0.002628   0.002997   0.000018   0.000061  -0.003608
            # and so forth... with blanks lines between blocks of 5 orbitals each.
            # Warning! There are subtle differences between GAMESS-US and PC-GAMES
            #   in the formatting of the first four columns.
            #
            # Watch out for F orbitals...
            # PC GAMESS
            #   19  C   1 YZ   0.000000   0.000000   0.000000   0.000000   0.000000
            #   20  C    XXX   0.000000   0.000000   0.000000   0.000000   0.002249
            #   21  C    YYY   0.000000   0.000000  -0.025555   0.000000   0.000000
            #   22  C    ZZZ   0.000000   0.000000   0.000000   0.002249   0.000000
            #   23  C    XXY   0.000000   0.000000   0.001343   0.000000   0.000000
            # GAMESS US
            #   55  C  1 XYZ   0.000000   0.000000   0.000000   0.000000   0.000000
            #   56  C  1XXXX  -0.000014  -0.000067   0.000000   0.000000   0.000000
            #
            # This is fine for GeoOpt and SP, but may be weird for TD and Freq.

            # This is the stuff that we can read from these blocks.
            self.moenergies = [[]]
            self.mosyms = [[]]
            if not hasattr(self, "nmo"):
                self.nmo = self.nbasis
            self.mocoeffs = [numpy.zeros((self.nmo, self.nbasis), "d")]
            readatombasis = False
            if not hasattr(self, "atombasis"):
                self.atombasis = []
                self.aonames = []
                for i in range(self.natom):
                    self.atombasis.append([])
                self.aonames = []
                readatombasis = True

            dashes = inputfile.next()
            for base in range(0, self.nmo, 5):
                blank = inputfile.next()
                line = inputfile.next() # Eigenvector numbers.
                line = inputfile.next() # Eigenvalues for these orbitals (in hartrees).
                self.moenergies[0].extend([utils.convertor(float(x), "hartree", "eV") for x in line.split()])
                line = inputfile.next() # Orbital symmetries.
                self.mosyms[0].extend(map(self.normalisesym, line.split()))
                
                # Now we have nbasis lines.
                # Going to use the same method as for normalise_aonames()
                # to extract basis set information.
                p = re.compile("(\d+)\s*([A-Z][A-Z]?)\s*(\d+)\s*([A-Z]+)")
                oldatom ='0'
                for i in range(self.nbasis):
                    line = inputfile.next()
                    # Fill atombasis and aonames only first time around
                    if readatombasis and base == 0:
                        aonames = []
                        start = line[:17].strip()
                        m = p.search(start)
                        if m:
                            g = m.groups()
                            aoname = "%s%s_%s" % (g[1].capitalize(), g[2], g[3])
                            oldatom = g[2]
                            atomno = int(g[2])-1
                            orbno = int(g[0])-1
                        else: # For F orbitals, as shown above
                            g = [x.strip() for x in line.split()]
                            aoname = "%s%s_%s" % (g[1].capitalize(), oldatom, g[2])
                            atomno = int(oldatom)-1
                            orbno = int(g[0])-1
                        self.atombasis[atomno].append(orbno)
                        self.aonames.append(aoname)
                    coeffs = line[15:] # Strip off the crud at the start.
                    j = 0
                    while j*11+4 < len(coeffs):
                        self.mocoeffs[0][base+j, i] = float(coeffs[j * 11:(j + 1) * 11])
                        j += 1

            line = inputfile.next()
            # If it's restricted we have:
            #  ...... END OF RHF CALCULATION ......
            #                or
            #  ...... END OF DFT CALCULATION ......
            # If it's unrestricted we have:
            #
            #  ----- BETA SET ----- 
            #
            #          ------------
            #          EIGENVECTORS
            #          ------------
            #
            #                      1          2          3          4          5
            # ... and so forth.
            if not "END OF" in line:
                self.mocoeffs.append(numpy.zeros((self.nmo, self.nbasis), "d"))
                self.moenergies.append([])
                self.mosyms.append([])
                for i in range(5):
                    line = inputfile.next()
                for base in range(0, self.nmo, 5):
                    blank = inputfile.next()
                    line = inputfile.next() # Eigenvector no
                    line = inputfile.next()
                    self.moenergies[1].extend([utils.convertor(float(x), "hartree", "eV") for x in line.split()])
                    line = inputfile.next()
                    self.mosyms[1].extend(map(self.normalisesym, line.split()))
                    for i in range(self.nbasis):
                        line = inputfile.next()
                        temp = line[15:] # Strip off the crud at the start
                        j = 0
                        while j * 11 + 4 < len(temp):
                            self.mocoeffs[1][base+j, i] = float(temp[j * 11:(j + 1) * 11])
                            j += 1
                line = inputfile.next()
            assert line.find("END OF") >= 0
            self.moenergies = [numpy.array(x, "d") for x in self.moenergies]

        if line.find("NUMBER OF OCCUPIED ORBITALS") >= 0:
            homos = [int(line.split()[-1])-1]
            line = inputfile.next()
            homos.append(int(line.split()[-1])-1)
            # Note that we cannot trust this self.homos until we come to
            # a line that contains the phrase:
            # "SYMMETRIES FOR INITAL GUESS ORBITALS FOLLOW"
            # which either is followed by "ALPHA" or "BOTH"
            # at which point we can say for certain that it is an
            # un/restricted calculations
            self.homos = numpy.array(homos, "i")

        if line.find("SYMMETRIES FOR INITIAL GUESS ORBITALS FOLLOW") >= 0:
            # Not unrestricted, so lop off the second index
            if line.find("BOTH SET(S)") >= 0:
                self.homos = numpy.resize(self.homos, [1])

        if line.find("TOTAL NUMBER OF ATOMS") == 1:
            self.natom = int(line.split()[-1])
            
        if line.find("NUMBER OF CARTESIAN GAUSSIAN BASIS") == 1 or line.find("TOTAL NUMBER OF BASIS FUNCTIONS") == 1:
            # The first is from Julien's Example and the second is from Alexander's
            # I think it happens if you use a polar basis function instead of a cartesian one
            self.nbasis = int(line.strip().split()[-1])
                
        elif line.find("SPHERICAL HARMONICS KEPT IN THE VARIATION SPACE") >= 0:
            # Note that this line is present if ISPHER=1, e.g. for C_bigbasis
            self.nmo = int(line.strip().split()[-1])
            
        elif line.find("TOTAL NUMBER OF MOS IN VARIATION SPACE") == 1:
            # Note that this line is not always present, so by default
            # NBsUse is set equal to NBasis (see below).
            self.nmo = int(line.split()[-1])

        elif line.find("OVERLAP MATRIX") == 0 or line.find("OVERLAP MATRIX") == 1:
            # The first is for PC-GAMESS, the second for GAMESS
            # Read 1-electron overlap matrix
            if not hasattr(self, "aooverlaps"):
                self.aooverlaps = numpy.zeros((self.nbasis, self.nbasis), "d")
            else:
                self.logger.info("Reading additional aooverlaps...")
            base = 0
            while base < self.nbasis:
                blank = inputfile.next()
                line = inputfile.next() # Basis fn number
                blank = inputfile.next()
                for i in range(self.nbasis - base): # Fewer lines each time
                    line = inputfile.next()
                    temp = line.split()
                    for j in range(4, len(temp)):
                        self.aooverlaps[base+j-4, i+base] = float(temp[j])
                        self.aooverlaps[i+base, base+j-4] = float(temp[j])
                base += 5

        # ECP Pseudopotential information
        if "ECP POTENTIALS" in line:
            if not hasattr(self, "coreelectrons"):
                self.coreelectrons = [0]*self.natom
            dashes = inputfile.next()
            blank = inputfile.next()
            header = inputfile.next()
            while header.split()[0] == "PARAMETERS":
                name = header[17:25]
                atomnum = int(header[34:40])
                # The pseudopotnetial is given explicitely
                if header[40:50] == "WITH ZCORE":
                  zcore = int(header[50:55])
                  lmax = int(header[63:67])
                  self.coreelectrons[atomnum-1] = zcore
                # The pseudopotnetial is copied from another atom
                if header[40:55] == "ARE THE SAME AS":
                  atomcopy = int(header[60:])
                  self.coreelectrons[atomnum-1] = self.coreelectrons[atomcopy-1]
                line = inputfile.next()
                while line.split() <> []:
                    line = inputfile.next()
                header = inputfile.next()

        # This was used before refactoring the parser, geotargets was set here after parsing.
        #if not hasattr(self, "geotargets"):
        #    opttol = 1e-4
        #    self.geotargets = numpy.array([opttol, 3. / opttol], "d")
        #if hasattr(self,"geovalues"): self.geovalues = numpy.array(self.geovalues, "d")

        
if __name__ == "__main__":
    import doctest, gamessparser
    doctest.testmod(gamessparser, verbose=False)
