
# Ifc2CA - IFC Code_Aster utility
# Copyright (C) 2020, 2021 Ioannis P. Christovasilis <ipc@aethereng.com>
#
# This file is part of Ifc2CA.
#
# Ifc2CA is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ifc2CA is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Ifc2CA.  If not, see <http://www.gnu.org/licenses/>.

import json
import numpy as np
import itertools

flatten = itertools.chain.from_iterable


class COMMANDFILE:
    def __init__(self, dataFilename, asterFilename):
        self.dataFilename = dataFilename
        self.asterFilename = asterFilename
        self.create()

    def getGroupName(self, name):
        info = name.split("|")
        sortName = "".join(c for c in info[0] if c.isupper())
        return str(sortName + "_" + info[1])

    def create(self):

        AccelOfGravity = 9.806  # m/sec^2

        # Read data from input file
        with open(self.dataFilename) as dataFile:
            data = json.load(dataFile)

        elements = data["elements"]
        connections = data["connections"]
        # --> Delete this reference data and repopulate it with the objects
        # while going through elements
        for conn in connections:
            conn["relatedElements"] = []
            self.calculateRestraints(conn)
        for el in elements:
            for rel in el["connections"]:
                conn = [
                    c for c in connections if c["ifcName"] == rel["relatedConnection"]
                ][0]
                rel["conn_string"] = None
                if conn["geometryType"] == "point":
                    rel["conn_string"] = "_0DC_"
                    rel["springGroupName"] = (
                        self.getGroupName(rel["relatingElement"])
                        + "_1DS_"
                        + self.getGroupName(rel["relatedConnection"])
                    )
                if conn["geometryType"] == "line":
                    rel["conn_string"] = "_1DC_"
                    rel["springGroupName"] = None
                if conn["geometryType"] == "surface":
                    rel["conn_string"] = "_2DC_"
                    rel["springGroupName"] = None

                rel["groupName1"] = (
                    self.getGroupName(rel["relatingElement"])
                    + rel["conn_string"]
                    + self.getGroupName(rel["relatedConnection"])
                )
                if rel["eccentricity"]:
                    rel["groupName2"] = (
                        self.getGroupName(rel["relatedConnection"])
                        + "_0DC_"
                        + self.getGroupName(rel["relatingElement"])
                    )
                    rel["index"] = len(conn["relatedElements"]) + 1
                    rel["unifiedGroupName"] = (
                        self.getGroupName(rel["relatedConnection"])
                        + "_0DC_%g" % rel["index"]
                    )
                else:
                    rel["groupName2"] = self.getGroupName(rel["relatedConnection"])
                self.calculateConstraints(rel)
                conn["relatedElements"].append(rel)
        # End <--

        materials = data["db"]["materials"]
        profiles = data["db"]["profiles"]

        edgeGroupNames = tuple(
            [
                self.getGroupName(el["ifcName"])
                for el in elements
                if el["geometryType"] == "line"
            ]
        )
        faceGroupNames = tuple(
            [
                self.getGroupName(el["ifcName"])
                for el in elements
                if el["geometryType"] == "surface"
            ]
        )
        point0DGroupNames = tuple(
            [
                self.getGroupName(el["ifcName"]) + "_0D"
                for el in connections
                if el["geometryType"] == "point"
            ]
        )
        spring1DGroupNames = tuple(
            flatten(
                [
                    [
                        rel["springGroupName"]
                        for rel in el["connections"]
                        if rel["springGroupName"]
                    ]
                    for el in elements
                ]
            )
        )
        point1DGroupNames = tuple(
            [
                self.getGroupName(el["ifcName"]) + "_0D"
                for el in connections
                if el["geometryType"] == "line"
            ]
        )

        unifiedConnection = False
        rigidLinkGroupNames = []
        for conn in connections:
            conn["unifiedGroupNames"] = [
                rel["unifiedGroupName"]
                for rel in conn["relatedElements"]
                if rel["eccentricity"]
            ]
            # if not conn['appliedCondition'] and len(conn['unifiedGroupNames']) == 1:
            #     conn['appliedCondition'] = {
            #         'dx': True,
            #         'dy': True,
            #         'dz': True
            #     }
            if len(conn["unifiedGroupNames"]) >= 1:
                conn["unifiedGroupNames"].insert(0, self.getGroupName(conn["ifcName"]))
                conn["unifiedGroupNames"] = tuple(conn["unifiedGroupNames"])
                unifiedConnection = True
            rigidLinkGroupNames.extend(
                [
                    self.getGroupName(rel["relatingElement"])
                    + "_1DR_"
                    + self.getGroupName(conn["ifcName"])
                    for rel in conn["relatedElements"]
                    if rel["eccentricity"]
                ]
            )
        rigidLinkGroupNames = tuple(rigidLinkGroupNames)

        # Define file to write command file for code_aster
        f = open(self.asterFilename, "w")

        f.write("# Command file generated by IfcOpenShell/ifc2ca scripts\n")
        f.write("\n")

        f.write("# Linear Static Analysis With Self-Weight\n")

        f.write(
            """
# STEP: INITIALIZE STUDY
DEBUT(
    PAR_LOT = 'NON'
)
"""
        )

        f.write(
            """
# STEP: READ MED FILE
mesh = LIRE_MAILLAGE(
    FORMAT = 'MED',
    UNITE = 20
)
"""
        )

        f.write(
            """
# STEP: DEFINE MODEL
model = AFFE_MODELE(
    MAILLAGE = mesh,
    AFFE = (
        _F(
            TOUT = 'OUI',
            PHENOMENE = 'MECANIQUE',
            MODELISATION = '3D'
        ),"""
        )

        if faceGroupNames:
            template = """
        _F(
            GROUP_MA = {groupNames},
            PHENOMENE = 'MECANIQUE',
            MODELISATION = 'DKT'
        ),"""

            context = {"groupNames": faceGroupNames}

            f.write(template.format(**context))

        if edgeGroupNames:
            template = """
        _F(
            GROUP_MA = {groupNames},
            PHENOMENE = 'MECANIQUE',
            MODELISATION = 'POU_D_E'
        ),"""

            context = {"groupNames": edgeGroupNames}

            f.write(template.format(**context))

        if point0DGroupNames:
            template = """
        _F(
            GROUP_MA = {groupNames},
            PHENOMENE = 'MECANIQUE',
            MODELISATION = 'DIS_TR'
        ),"""

            context = {
                "groupNames": tuple(flatten([point0DGroupNames, spring1DGroupNames]))
            }

            f.write(template.format(**context))

        if point1DGroupNames:
            template = """
        _F(
            GROUP_MA = {groupNames},
            PHENOMENE = 'MECANIQUE',
            MODELISATION = 'DIS_TR'
        ),"""

            context = {"groupNames": point1DGroupNames}

            f.write(template.format(**context))

        if rigidLinkGroupNames:
            template = """
        _F(
            GROUP_MA = {groupNames},
            PHENOMENE = 'MECANIQUE',
            MODELISATION = 'POU_D_E'
        ),"""

            context = {"groupNames": rigidLinkGroupNames}

            f.write(template.format(**context))

        f.write(
            """
    )
)\n
"""
        )

        f.write("# STEP: DEFINE MATERIALS")

        for i, material in enumerate(materials):
            template = """
{matNameID} = DEFI_MATERIAU(
    ELAS = _F(
        E = {youngModulus},
        NU = {poissonRatio},
        RHO = {massDensity}
    )
)
"""
            if "poissonRatio" in material["mechProps"]:
                poissonRatio = material["mechProps"]["poissonRatio"]
            else:
                if "shearModulus" in material["mechProps"]:
                    poissonRatio = (
                        material["mechProps"]["youngModulus"]
                        / 2.0
                        / material["mechProps"]["shearModulus"]
                    ) - 1
                else:
                    poissonRatio = 0.0

            context = {
                "matNameID": "mat" + "_%s" % i,
                "youngModulus": float(material["mechProps"]["youngModulus"]),
                "poissonRatio": float(poissonRatio),
                "massDensity": float(material["commonProps"]["massDensity"]),
            }

            f.write(template.format(**context))

        f.write(
            """
material = AFFE_MATERIAU(
    MAILLAGE = mesh,
    AFFE = ("""
        )

        for i, material in enumerate(materials):
            template = """
        _F(
            GROUP_MA = {groupNames},
            MATER = {matNameID},
        ),"""

            context = {
                "groupNames": tuple(
                    [self.getGroupName(rel) for rel in material["relatedElements"]]
                ),
                "matNameID": "mat" + "_%s" % i,
            }

            f.write(template.format(**context))

        if rigidLinkGroupNames:
            template = """
        _F(
            GROUP_MA = {groupNames},
            MATER = {matNameID},
        ),"""

            context = {"groupNames": rigidLinkGroupNames, "matNameID": "mat_0"}

            f.write(template.format(**context))

        f.write(
            """
    )
)
"""
        )

        f.write(
            """
# STEP: DEFINE ELEMENTS
element = AFFE_CARA_ELEM(
    MODELE = model,
    POUTRE = ("""
        )

        for profile in profiles:
            if (
                profile["profileShape"] == "rectangular"
                and profile["profileType"] == "AREA"
            ):
                template = """
        _F(
            GROUP_MA = {groupNames},
            SECTION = 'RECTANGLE',
            CARA = ('HY', 'HZ'),
            VALE = {profileDimensions}
        ),"""

                context = {
                    "groupNames": tuple(
                        [self.getGroupName(rel) for rel in profile["relatedElements"]]
                    ),
                    "profileDimensions": (profile["xDim"], profile["yDim"]),
                }

                f.write(template.format(**context))

            elif (
                profile["profileShape"] == "iSymmetrical"
                and profile["profileType"] == "AREA"
            ):
                template = """
        _F(
            GROUP_MA = {groupNames},
            SECTION = 'GENERALE',
            CARA = ('A', 'IY', 'IZ', 'JX'),
            VALE = {profileProperties}
        ),"""

                context = {
                    "groupNames": tuple(
                        [self.getGroupName(rel) for rel in profile["relatedElements"]]
                    ),
                    "profileProperties": (
                        profile["mechProps"]["crossSectionArea"],
                        profile["mechProps"]["momentOfInertiaY"],
                        profile["mechProps"]["momentOfInertiaZ"],
                        profile["mechProps"]["torsionalConstantX"],
                    ),
                }

                f.write(template.format(**context))

        if rigidLinkGroupNames:
            template = """
        _F(
            GROUP_MA = {groupNames},
            SECTION = 'RECTANGLE',
            CARA = ('HY', 'HZ'),
            VALE = {profileDimensions}
        ),"""

            context = {"groupNames": rigidLinkGroupNames, "profileDimensions": (1, 1)}

            f.write(template.format(**context))

        f.write(
            """
    ),
    COQUE = ("""
        )

        for el in [el for el in elements if el["geometryType"] == "surface"]:

            template = """
        _F(
            GROUP_MA = '{groupName}',
            EPAIS = {thickness},
            VECTEUR = {localAxisX}
        ),"""

            context = {
                "groupName": self.getGroupName(el["ifcName"]),
                "thickness": el["thickness"],
                "localAxisX": tuple(el["orientation"][0]),
            }

            f.write(template.format(**context))

        f.write(
            """
    ),"""
        )
        f.write(
            """
    DISCRET = ("""
        )

        for conn in [conn for conn in connections if conn["geometryType"] == "point"]:

            template = """
        _F(
            GROUP_MA = '{groupName}',
            CARA = 'K_TR_D_N',
            VALE = {stiffnesses},
            REPERE = 'LOCAL'
        ),"""

            context = {
                "groupName": self.getGroupName(conn["ifcName"]) + "_0D",
                "stiffnesses": conn["stiffnesses"],
            }

            f.write(template.format(**context))

            for rel in conn["relatedElements"]:

                template = """
        _F(
            GROUP_MA = '{groupName}',
            CARA = 'K_TR_D_L',
            VALE = {stiffnesses},
            REPERE = 'LOCAL'
        ),"""

                context = {
                    "groupName": rel["springGroupName"],
                    "stiffnesses": rel["stiffnesses"],
                }

                f.write(template.format(**context))

        for conn in [conn for conn in connections if conn["geometryType"] == "line"]:

            template = """
        _F(
            GROUP_MA = '{groupName}',
            CARA = 'K_TR_D_N',
            VALE = {stiffnesses},
            REPERE = 'LOCAL'
        ),"""

            context = {
                "groupName": self.getGroupName(conn["ifcName"]) + "_0D",
                "stiffnesses": conn["stiffnesses"],
            }

            f.write(template.format(**context))

        f.write(
            """
    ),"""
        )

        f.write(
            """
    ORIENTATION = ("""
        )

        for el in [el for el in elements if el["geometryType"] == "line"]:

            template = """
        _F(
            GROUP_MA = '{groupName}',
            CARA = 'VECT_Y',
            VALE = {localAxisY}
        ),"""

            context = {
                "groupName": self.getGroupName(el["ifcName"]),
                "localAxisY": tuple(el["orientation"][1]),
            }

            f.write(template.format(**context))

        for conn in [conn for conn in connections if conn["geometryType"] == "point"]:

            template = """
        _F(
            GROUP_MA = '{groupName}',
            CARA = 'VECT_X_Y',
            VALE = {localAxesXY}
        ),"""

            context = {
                "groupName": self.getGroupName(conn["ifcName"]) + "_0D",
                "localAxesXY": tuple(conn["orientation"][0] + conn["orientation"][1]),
            }

            f.write(template.format(**context))

            for rel in conn["relatedElements"]:

                template = """
        _F(
            GROUP_MA = '{groupName}',
            CARA = 'VECT_X_Y',
            VALE = {localAxesXY}
        ),"""

                context = {
                    "groupName": rel["springGroupName"],
                    "localAxesXY": tuple(rel["orientation"][0] + rel["orientation"][1]),
                }

                f.write(template.format(**context))

        for conn in [conn for conn in connections if conn["geometryType"] == "line"]:

            template = """
        _F(
            GROUP_MA = '{groupName}',
            CARA = 'VECT_X_Y',
            VALE = {localAxesXY}
        ),"""

            context = {
                "groupName": self.getGroupName(conn["ifcName"]) + "_0D",
                "localAxesXY": tuple(conn["orientation"][0] + conn["orientation"][1]),
            }

            f.write(template.format(**context))

        f.write(
            """
    ),"""
        )

        f.write(
            """
)\n
"""
        )

        f.write("# STEP: DEFINE SUPPORTS AND CONSTRAINTS")

        f.write(
            """
liaisons = AFFE_CHAR_MECA(
    MODELE = model,
    LIAISON_DDL = ("""
        )

        for conn in [conn for conn in connections if conn["geometryType"] == "point"]:
            if conn["appliedCondition"]:
                for i in range(len(conn["liaisons"]["coeffs"])):
                    template = """
        _F(
            GROUP_NO = {groupNames},
            DDL = {dofs},
            COEF_MULT = {coeffs},
            COEF_IMPO = 0.0
        ),"""

                    context = {
                        "groupNames": conn["liaisons"]["groupNames"],
                        "dofs": conn["liaisons"]["dofs"][i],
                        "coeffs": conn["liaisons"]["coeffs"][i],
                    }

                    f.write(template.format(**context))

            for rel in conn["relatedElements"]:
                for i in range(len(rel["liaisons"]["coeffs"])):
                    template = """
        _F(
            GROUP_NO = {groupNames},
            DDL = {dofs},
            COEF_MULT = {coeffs},
            COEF_IMPO = 0.0
        ),"""

                    context = {
                        "groupNames": rel["liaisons"]["groupNames"],
                        "dofs": rel["liaisons"]["dofs"][i],
                        "coeffs": rel["liaisons"]["coeffs"][i],
                    }

                    f.write(template.format(**context))

        f.write(
            """
    ),"""
        )

        f.write(
            """
    LIAISON_GROUP = ("""
        )

        for conn in [conn for conn in connections if conn["geometryType"] == "line"]:
            if conn["appliedCondition"]:
                for i in range(len(conn["liaisons"]["coeffs"])):
                    template = """
        _F(
            GROUP_NO_1 = {groupName_1},
            GROUP_NO_2 = {groupName_1},
            DDL_1 = {dofs},
            DDL_2 = {dofs},
            COEF_MULT_1 = {coeffs},
            COEF_MULT_2 = (0.0, 0.0, 0.0),
            COEF_IMPO = 0.0
        ),"""

                    context = {
                        "groupName_1": tuple([conn["liaisons"]["groupNames"][0]]),
                        "dofs": conn["liaisons"]["dofs"][i],
                        "coeffs": conn["liaisons"]["coeffs"][i],
                    }

                    f.write(template.format(**context))

            for rel in conn["relatedElements"]:
                for i in range(len(rel["liaisons"]["coeffs"])):
                    template = """
        _F(
            GROUP_NO_1 = {groupName_1},
            GROUP_NO_2 = {groupName_2},
            DDL_1 = {dofs},
            DDL_2 = {dofs},
            COEF_MULT_1 = {coeffs_1},
            COEF_MULT_2 = {coeffs_2},
            COEF_IMPO = 0.0
        ),"""

                    context = {
                        "groupName_1": tuple([rel["liaisons"]["groupNames"][0]]),
                        "groupName_2": tuple([rel["liaisons"]["groupNames"][3]]),
                        "dofs": tuple(list(rel["liaisons"]["dofs"][i])[:3]),
                        "coeffs_1": tuple(list(rel["liaisons"]["coeffs"][i])[:3]),
                        "coeffs_2": tuple(list(rel["liaisons"]["coeffs"][i])[3:]),
                    }

                    f.write(template.format(**context))

        f.write(
            """
    ),"""
        )

        if unifiedConnection:
            f.write(
                """
    LIAISON_UNIF = ("""
            )

            for conn in [
                conn for conn in connections if len(conn["unifiedGroupNames"]) > 1
            ]:
                template = """
        _F(
            GROUP_NO = {groupNames},
            DDL = ('DX', 'DY', 'DZ', 'DRX', 'DRY', 'DRZ')
        ),"""

                context = {"groupNames": conn["unifiedGroupNames"]}

                f.write(template.format(**context))

            f.write(
                """
    ),"""
            )

        if rigidLinkGroupNames:
            f.write(
                """
    LIAISON_SOLIDE = ("""
            )

            for groupName in rigidLinkGroupNames:
                template = """
        _F(
            GROUP_MA = '{groupName}'
        ),"""

                context = {"groupName": groupName}

                f.write(template.format(**context))

            f.write(
                """
    ),"""
            )

        f.write(
            """
)
"""
        )

        template = """
# STEP: DEFINE LOAD
gravLoad = AFFE_CHAR_MECA(
    MODELE = model,
    PESANTEUR = _F(
        GRAVITE = {AccelOfGravity},
        DIRECTION = (0.0, 0.0, -1.0)
    )
)
"""
        context = {
            "AccelOfGravity": AccelOfGravity,
        }

        f.write(template.format(**context))

        f.write(
            """
# STEP: RUN ANALYSIS
res_Bld = MECA_STATIQUE(
    MODELE = model,
    CHAM_MATER = material,
    CARA_ELEM = element,
    EXCIT = (
        _F(
            CHARGE = liaisons
        ),
        _F(
            CHARGE = gravLoad
        )
    )
)
"""
        )

        #         f.write(
        # '''
        # # STEP: POST-PROCESSING
        # res_Bld = CALC_CHAMP(
        #     reuse = res_Bld,
        #     RESULTAT = res_Bld,
        #     # CONTRAINTE = ('SIEF_ELNO', 'SIGM_ELNO', 'EFGE_ELNO',),
        #     FORCE = ('REAC_NODA', 'FORC_NODA',)
        # )
        # '''
        #         )
        #
        #         template = \
        # '''
        # # STEP: MASS EXTRACTION FOR EACH ASSEMBLE
        # FaceMass = POST_ELEM(
        # 	TITRE = 'TotMass',
        #     MODELE = model,
        #     CARA_ELEM = element,
        #     CHAM_MATER = material,
        #     MASS_INER = _F(
        #         GROUP_MA = {massList},
        #     ),
        # )\n'''
        #
        #         context = {
        #             'massList': massList,
        #         }
        #
        #         f.write(template.format(**context))
        #
        #         f.write(
        # '''
        # IMPR_TABLE(
        #     UNITE = 10,
        # 	TABLE = FaceMass,
        #     SEPARATEUR = ',',
        #     NOM_PARA = ('LIEU', 'MASSE', 'CDG_X', 'CDG_Y', 'CDG_Z'),
        # 	# FORMAT_R = '1PE15.6',
        # )
        # '''
        #         )
        #
        #         template = \
        # '''
        # # STEP: REACTION EXTRACTION AT THE BASE
        # Reacs = POST_RELEVE_T(
        #     ACTION = _F(
        #         INTITULE = 'sumReac',
        #         GROUP_NO = {groupNames},
        #         RESULTAT = res_Bld,
        #         NOM_CHAM = 'REAC_NODA',
        #         RESULTANTE = ('DX','DY','DZ',),
        #         MOMENT = ('DRX','DRY','DRZ',),
        #         POINT = (0,0,0,),
        #         OPERATION = 'EXTRACTION'
        #     )
        # )
        # '''
        #
        #         context = {
        #             'groupNames': point0DGroupNames,
        #         }
        #
        #         f.write(template.format(**context))
        #
        #         f.write(
        # '''
        # IMPR_TABLE(
        #     UNITE = 10,
        #     TABLE = Reacs,
        #     SEPARATEUR = ',',
        #     # NOM_PARA = ('INTITULE', 'RESU', 'NOM_CHAM', 'INST', 'DX','DY','DZ'),
        #     FORMAT_R = '1PE12.3',
        # )
        # '''
        #         )
        #
        f.write(
            """
# STEP: DEFORMED SHAPE EXTRACTION
IMPR_RESU(
    FORMAT = 'MED',
	UNITE = 80,
	RESU = _F(
 		RESULTAT = res_Bld,
 		NOM_CHAM = ('DEPL',), # 'REAC_NODA', 'FORC_NODA',
 		NOM_CHAM_MED = ('Bld_DISP',), #  'Bld_REAC', 'Bld_FORC'
    )
)
"""
        )

        f.write(
            """
# STEP: CONCLUDE STUDY
FIN()
"""
        )

        f.close()

    def calculateConstraints(self, rel):
        gr1 = rel["groupName1"]
        gr2 = rel["groupName2"]
        o = np.array(rel["orientation"]).transpose().tolist()
        liaisons = {
            "groupNames": (gr1, gr1, gr1, gr2, gr2, gr2),
            "coeffs": [],
            "dofs": [],
        }
        stiffnesses = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        if not rel["appliedCondition"]:
            rel["appliedCondition"] = {
                "dx": True,
                "dy": True,
                "dz": True,
                "drx": True,
                "dry": True,
                "drz": True,
            }
        if (
            isinstance(rel["appliedCondition"]["dx"], bool)
            and rel["appliedCondition"]["dx"]
        ):
            liaisons["coeffs"].append(
                (o[0][0], o[1][0], o[2][0], -o[0][0], -o[1][0], -o[2][0])
            )
            liaisons["dofs"].append(("DX", "DY", "DZ", "DX", "DY", "DZ"))
        elif (
            isinstance(rel["appliedCondition"]["dx"], float)
            and rel["appliedCondition"]["dx"] > 0
        ):
            stiffnesses[0] = rel["appliedCondition"]["dx"]

        if (
            isinstance(rel["appliedCondition"]["dy"], bool)
            and rel["appliedCondition"]["dy"]
        ):
            liaisons["coeffs"].append(
                (o[0][1], o[1][1], o[2][1], -o[0][1], -o[1][1], -o[2][1])
            )
            liaisons["dofs"].append(("DX", "DY", "DZ", "DX", "DY", "DZ"))
        elif (
            isinstance(rel["appliedCondition"]["dy"], float)
            and rel["appliedCondition"]["dy"] > 0
        ):
            stiffnesses[1] = rel["appliedCondition"]["dy"]

        if (
            isinstance(rel["appliedCondition"]["dz"], bool)
            and rel["appliedCondition"]["dz"]
        ):
            liaisons["coeffs"].append(
                (o[0][2], o[1][2], o[2][2], -o[0][2], -o[1][2], -o[2][2])
            )
            liaisons["dofs"].append(("DX", "DY", "DZ", "DX", "DY", "DZ"))
        elif (
            isinstance(rel["appliedCondition"]["dz"], float)
            and rel["appliedCondition"]["dz"] > 0
        ):
            stiffnesses[2] = rel["appliedCondition"]["dz"]

        if (
            isinstance(rel["appliedCondition"]["drx"], bool)
            and rel["appliedCondition"]["drx"]
        ):
            liaisons["coeffs"].append(
                (o[0][0], o[1][0], o[2][0], -o[0][0], -o[1][0], -o[2][0])
            )
            liaisons["dofs"].append(("DRX", "DRY", "DRZ", "DRX", "DRY", "DRZ"))
        elif (
            isinstance(rel["appliedCondition"]["drx"], float)
            and rel["appliedCondition"]["drx"] > 0
        ):
            stiffnesses[3] = rel["appliedCondition"]["drx"]

        if (
            isinstance(rel["appliedCondition"]["dry"], bool)
            and rel["appliedCondition"]["dry"]
        ):
            liaisons["coeffs"].append(
                (o[0][1], o[1][1], o[2][1], -o[0][1], -o[1][1], -o[2][1])
            )
            liaisons["dofs"].append(("DRX", "DRY", "DRZ", "DRX", "DRY", "DRZ"))
        elif (
            isinstance(rel["appliedCondition"]["dry"], float)
            and rel["appliedCondition"]["dry"] > 0
        ):
            stiffnesses[4] = rel["appliedCondition"]["dry"]

        if (
            isinstance(rel["appliedCondition"]["drz"], bool)
            and rel["appliedCondition"]["drz"]
        ):
            liaisons["coeffs"].append(
                (o[0][2], o[1][2], o[2][2], -o[0][2], -o[1][2], -o[2][2])
            )
            liaisons["dofs"].append(("DRX", "DRY", "DRZ", "DRX", "DRY", "DRZ"))
        elif (
            isinstance(rel["appliedCondition"]["drz"], float)
            and rel["appliedCondition"]["drz"] > 0
        ):
            stiffnesses[5] = rel["appliedCondition"]["drz"]

        rel["liaisons"] = liaisons
        rel["stiffnesses"] = tuple(stiffnesses)

    def calculateRestraints(self, conn):
        group = self.getGroupName(conn["ifcName"])
        o = np.array(conn["orientation"]).transpose().tolist()
        liaisons = {"groupNames": (group, group, group), "coeffs": [], "dofs": []}
        stiffnesses = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        if not conn["appliedCondition"]:
            conn["liaisons"] = liaisons
            conn["stiffnesses"] = tuple(stiffnesses)
            return

        if (
            isinstance(conn["appliedCondition"]["dx"], bool)
            and conn["appliedCondition"]["dx"]
        ):
            liaisons["coeffs"].append((o[0][0], o[1][0], o[2][0]))
            liaisons["dofs"].append(("DX", "DY", "DZ"))
        elif (
            isinstance(conn["appliedCondition"]["dx"], float)
            and conn["appliedCondition"]["dx"] > 0
        ):
            stiffnesses[0] = conn["appliedCondition"]["dx"]

        if (
            isinstance(conn["appliedCondition"]["dy"], bool)
            and conn["appliedCondition"]["dy"]
        ):
            liaisons["coeffs"].append((o[0][1], o[1][1], o[2][1]))
            liaisons["dofs"].append(("DX", "DY", "DZ"))
        elif (
            isinstance(conn["appliedCondition"]["dy"], float)
            and conn["appliedCondition"]["dy"] > 0
        ):
            stiffnesses[1] = conn["appliedCondition"]["dy"]

        if (
            isinstance(conn["appliedCondition"]["dz"], bool)
            and conn["appliedCondition"]["dz"]
        ):
            liaisons["coeffs"].append((o[0][2], o[1][2], o[2][2]))
            liaisons["dofs"].append(("DX", "DY", "DZ"))
        elif (
            isinstance(conn["appliedCondition"]["dz"], float)
            and conn["appliedCondition"]["dz"] > 0
        ):
            stiffnesses[2] = conn["appliedCondition"]["dz"]

        if (
            isinstance(conn["appliedCondition"]["drx"], bool)
            and conn["appliedCondition"]["drx"]
        ):
            liaisons["coeffs"].append((o[0][0], o[1][0], o[2][0]))
            liaisons["dofs"].append(("DRX", "DRY", "DRZ"))
        elif (
            isinstance(conn["appliedCondition"]["drx"], float)
            and conn["appliedCondition"]["drx"] > 0
        ):
            stiffnesses[3] = conn["appliedCondition"]["drx"]

        if (
            isinstance(conn["appliedCondition"]["dry"], bool)
            and conn["appliedCondition"]["dry"]
        ):
            liaisons["coeffs"].append((o[0][1], o[1][1], o[2][1]))
            liaisons["dofs"].append(("DRX", "DRY", "DRZ"))
        elif (
            isinstance(conn["appliedCondition"]["dry"], float)
            and conn["appliedCondition"]["dry"] > 0
        ):
            stiffnesses[4] = conn["appliedCondition"]["dry"]

        if (
            isinstance(conn["appliedCondition"]["drz"], bool)
            and conn["appliedCondition"]["drz"]
        ):
            liaisons["coeffs"].append((o[0][2], o[1][2], o[2][2]))
            liaisons["dofs"].append(("DRX", "DRY", "DRZ"))
        elif (
            isinstance(conn["appliedCondition"]["drz"], float)
            and conn["appliedCondition"]["drz"] > 0
        ):
            stiffnesses[5] = conn["appliedCondition"]["drz"]

        conn["liaisons"] = liaisons
        conn["stiffnesses"] = tuple(stiffnesses)


if __name__ == "__main__":
    fileNames = [
        "cantilever_01",
        "portal_01",
        "grid_of_beams",
        "slab_01",
        "structure_01",
    ]
    files = fileNames

    for fileName in files:
        BASE_PATH = "/home/jesusbill/Dev-Projects/github.com/IfcOpenShell/analysis-models/models/"
        DATAFILENAME = BASE_PATH + fileName + "/" + fileName + ".json"
        ASTERFILENAME = BASE_PATH + fileName + "/" + fileName + ".comm"
        COMMANDFILE(DATAFILENAME, ASTERFILENAME)
