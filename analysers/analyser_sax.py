#!/usr/bin/env python
#-*- coding: utf-8 -*-

###########################################################################
##                                                                       ##
## Copyrights Etienne Chové <chove@crans.org> 2009                       ##
##                                                                       ##
## This program is free software: you can redistribute it and/or modify  ##
## it under the terms of the GNU General Public License as published by  ##
## the Free Software Foundation, either version 3 of the License, or     ##
## (at your option) any later version.                                   ##
##                                                                       ##
## This program is distributed in the hope that it will be useful,       ##
## but WITHOUT ANY WARRANTY; without even the implied warranty of        ##
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         ##
## GNU General Public License for more details.                          ##
##                                                                       ##
## You should have received a copy of the GNU General Public License     ##
## along with this program.  If not, see <http://www.gnu.org/licenses/>. ##
##                                                                       ##
###########################################################################

from Analyser import Analyser

import re, sys, os
from modules import OsmoseLog
from modules import OsmoseErrorFile

###########################################################################

class Analyser_Sax(Analyser):

    def __init__(self, config, logger = OsmoseLog.logger()):
        Analyser.__init__(self, config, logger)

    def __enter__(self):
        # open database connections
        self._load_reader()
        self._load_parser()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # close database connections
        self._log(u"Closing reader and parser")
        del self.parser
        del self._reader

    def analyser(self):
        self._load_plugins()
        self._load_output()
        self._run_analyse()
        self._close_plugins()
        self._close_output()

    ################################################################################
    #### Useful functions

    def ToolsGetFilePath(self, filename):
        return os.path.join(self.config.dir_scripts, filename)

    def ToolsOpenFile(self, filename, mode):
        return open(self.ToolsGetFilePath(filename).encode("utf8"), mode)

    def ToolsListDir(self, dirname):
        return [x.decode("utf8") for x in os.listdir(self.ToolsGetFilePath(dirname))]

    def ToolsReadList(self, filename):
        f = self.ToolsOpenFile(filename, "r")
        d = []
        for x in f.readlines():
            x = x.strip().decode("utf-8")
            if not x: continue
            if x[0] == "#": continue
            d.append(x)
        f.close()
        return d

    def ToolsReadDict(self, filename, separator):
        f = self.ToolsOpenFile(filename, "r")
        d = {}
        for x in f.readlines():
            x = x.strip().decode("utf-8")
            if x and separator in x:
                x = x.split(separator)
                d[x[0]] = x[1]
        f.close()
        return d

    ################################################################################
    #### Reader

    def NodeGet(self, NodeId):
        return self._reader.NodeGet(NodeId)

    def WayGet(self, WayId):
        return self._reader.WayGet(WayId)

    def RelationGet(self, RelationId):
        return self._reader.RelationGet(RelationId)

    def UserGet(self, UserId):
        return self._reader.UserGet(UserId)

    def ExtendData(self, data):
        if "uid" in data and not "user" in data:
            user = self.UserGet(data["uid"])
            if user:
                data["user"] = user
        return data

    ################################################################################
    #### Logs

    def _log(self, txt):
        self.logger.log(txt)

    def _sublog(self, txt):
        self.logger.sub().log(txt)

    def _cpt(self, txt):
        self.logger.cpt(txt)

    def _subcpt(self, txt):
        self.logger.sub().cpt(txt)

    ################################################################################
    #### Node parsing

    def NodeCreate(self, data):

        # Initialisation
        err  = []
        tags = data[u"tag"]

        if tags == {}:
            return

        # On execute les jobs
        for meth in self.pluginsNodeMethodes:
            res = meth(data, tags)
            if res:
                err += res

        # Enregistrement des erreurs
        if err:
            data = self.ExtendData(data)
            for e in err:
                try:
                    fix = e[2].get("fix")
                    if e[2].get("fix"):
                        del(e[2]["fix"])
                    self.error_file.error(
                        e[0],
                        e[1],
                        e[2],
                        [data["id"]],
                        ["node"],
                        fix,
                        {"position": [data], "node": [data]})
                except:
                    print "Error on error", e, "from", err
                    raise

    def NodeUpdate(self, data):
        self.NodeDelete(data)
        self.NodeCreate(data)

    def NodeDelete(self, data):
        self.error_file.node_delete(data["id"])

    ################################################################################
    #### Way parsing

    def WayCreate(self, data):

        # Initialisation
        err  = []
        tags = data[u"tag"]
        nds  = data[u"nd"]

        # On execute les jobs
        for meth in self.pluginsWayMethodes:
            res = meth(data, tags, nds)
            if res:
                err += res

        # Enregistrement des erreurs
        if err:
            node = self.NodeGet(nds[len(nds)/2])
            if not node:
                node = {u"lat":0, u"lon":0}
            data = self.ExtendData(data)
            for e in err:
                try:
                    fix = e[2].get("fix")
                    if e[2].get("fix"):
                        del(e[2]["fix"])
                    self.error_file.error(
                        e[0],
                        e[1],
                        e[2],
                        [data["id"]],
                        ["way"],
                        fix,
                        {"position": [node], "way": [data]})
                except:
                    print "Error on error", e, "from", err
                    raise

    def WayUpdate(self, data):
        self.WayDelete(data)
        self.WayCreate(data)

    def WayDelete(self, data):
        self.error_file.way_delete(data["id"])

    ################################################################################
    #### Relation parsing

    def locateRelation(self, data):
        node = None
        for memb in data[u"member"]:
            if memb[u"type"] == u"node":
                node = self.NodeGet(memb[u"ref"])
            elif memb[u"type"] == "way":
                way = self.WayGet(memb[u"ref"])
                if way:
                    node = self.NodeGet(way[u"nd"][0])
            if node:
                break
        if not node:
            for memb in data[u"member"]:
                if memb[u"type"] == u"relation":
                    rel = self.RelationGet(memb[u"ref"])
                    if rel:
                        node = self.locateRelation(rel)
                if node:
                    break
        return node

    def RelationCreate(self, data):

        # Initialisation

        err  = []
        tags = data[u"tag"]
        members = data[u"member"]

        # On execute les jobs
        for meth in self.pluginsRelationMethodes:
            res = meth(data, tags, members)
            if res:
                err += res

        # Enregistrement des erreurs
        if err and data[u"member"]:
            node = self.locateRelation(data)
            if not node:
                node = {u"lat":0, u"lon":0}
            data = self.ExtendData(data)
            for e in err:
                try:
                    fix = e[2].get("fix")
                    if e[2].get("fix"):
                        del(e[2]["fix"])
                    self.error_file.error(
                        e[0],
                        e[1],
                        e[2],
                        [data["id"]],
                        ["relation"],
                        fix,
                        {"position": [node], "relation": [data]})
                except:
                    print "Error on error", e, "from", err
                    raise

    def RelationUpdate(self, data):
        self.RelationDelete(data)
        self.RelationCreate(data)

    def RelationDelete(self, data):
        self.error_file.relation_delete(data["id"])

    ################################################################################

    def _load_reader(self):
        if hasattr(self.config, 'db_string') and self.config.db_string:
            from modules import OsmOsis
            self._reader = OsmOsis.OsmOsis(self.config.db_string, self.config.db_schema)
            return

        try:
            from modules import OsmBin
            self._reader = OsmBin.OsmBin("/data/work/osmbin/data")
            return
        except IOError:
            pass

        from modules import OsmSaxAlea
        self._reader = OsmSaxAlea.OsmSaxReader(self.config.src)

    ################################################################################

    def _load_parser(self):
        if self.config.src.endswith(".pbf"):
            from modules.OsmPbf import OsmPbfReader
            self.parser = OsmPbfReader(self.config.src, self.logger.sub())
            self.parsing_change_file = False
        elif (self.config.src.endswith(".osc") or
              self.config.src.endswith(".osc.gz") or
              self.config.src.endswith(".osc.bz2")):
            from modules.OsmSax import OscSaxReader
            self.parser = OscSaxReader(self.config.src, self.logger.sub())
            self.parsing_change_file = True
        elif (self.config.src.endswith(".osm") or
              self.config.src.endswith(".osm.gz") or
              self.config.src.endswith(".osm.bz2")):
            from modules.OsmSax import OsmSaxReader
            self.parser = OsmSaxReader(self.config.src, self.logger.sub())
            self.parsing_change_file = False
        else:
            raise Exception, "File extension '%s' is not recognized" % self.config.src

    ################################################################################

    def _load_plugins(self):

        self._log(u"Loading plugins")
        self._Err = {}
        d = {}
        import plugins
        self.plugins = {}
        self.pluginsNodeMethodes = []
        self.pluginsWayMethodes = []
        self.pluginsRelationMethodes = []
        _order = ["pre_pre_","pre_", "", "post_", "post_post_"]
        _types = ["way", "node", "relation"]

        for x in _order:
            for y in _types:
                d[x+y] = []

        conf_limit = set()
        for i in ("country", "language"):
            if i in self.config.options:
                conf_limit.add(self.config.options[i])

        # load plugins
        re_desc = re.compile("^err_[0-9]+_[a-z]+$")
        re_item = re.compile("^err_[0-9]+$")
        for plugin in sorted(self.ToolsListDir("plugins")):
            if not plugin.endswith(".py") or plugin in ("__init__.py", "Plugin.py"):
                continue
            pluginName = plugin[:-3]
            __import__("plugins."+pluginName)
            pluginClazz = eval("plugins."+pluginName+"."+pluginName)

            if "only_for" in dir(pluginClazz):
                if conf_limit.isdisjoint(set(pluginClazz.only_for)):
                    self._sublog(u"skip "+plugin[:-3])
                    continue

            pluginInstance = pluginClazz(self)
            pluginAvailableMethodes = pluginInstance.availableMethodes()
            self.plugins[pluginName] = pluginInstance

            # Récupération des fonctions à appeler
            if "node" in pluginAvailableMethodes:
                self.pluginsNodeMethodes.append(pluginInstance.node)
            if "way" in pluginAvailableMethodes:
                self.pluginsWayMethodes.append(pluginInstance.way)
            if "relation" in pluginAvailableMethodes:
                self.pluginsRelationMethodes.append(pluginInstance.relation)

            # Initialisation du plugin
            self._sublog(u"init "+pluginName+" ("+", ".join(self.plugins[pluginName].availableMethodes())+")")
            self.plugins[pluginName].init(self.logger.sub().sub())

            # Liste des erreurs générées
            for (cl, v) in self.plugins[pluginName].errors.items():
                if cl in self._Err:
                    raise Exception, "class %d already present as item %d" % (cl, self._Err[cl]['item'])
                self._Err[cl] = v

    ################################################################################

    def _load_output(self):
        self.error_file = OsmoseErrorFile.ErrorFile(self.config)
        self.error_file.begin()
        self.error_file.analyser(change=self.parsing_change_file)

        # Création des classes dans le fichier des erreurs
        for (cl, item) in self._Err.items():
            self.error_file.classs(
                cl,
                item["item"],
                item.get("level"),
                item.get("tag"),
                item['desc'])

    ################################################################################

    def _run_analyse(self):
        self._log(u"Analyse des données: "+self.config.src)
        self.parser.CopyTo(self)
        self._log(u"Analyse terminée")

    ################################################################################

    def _close_plugins(self):
        # Fermeture des plugins
        self._log(u"Déchargement des Plugins")
        for y in sorted(self.plugins.keys()):
            self._sublog(u"end "+y)
            self.plugins[y].end(self.logger.sub().sub())

    def _close_output(self):
        self.error_file.analyser_end()
        self.error_file.end()

    ################################################################################


if __name__=="__main__":
    # Check argument
    if len(sys.argv)!=3:
        print "Syntax: analyser_sax.py <fichier_source.osm> <fichier_dest.xml.bz2>"
        sys.exit(-1)

    # Prepare configuration
    class config:
        dir_scripts = '.'
        options = {"country": "FR", "language": "fr"}
        src = sys.argv[1]
        dst = sys.argv[2]
        polygon_id = None

    # Start analyser
    with Analyser_Sax(config()) as analyser_obj:
        analyser_obj.analyser()
