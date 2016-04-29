import binascii
import itertools
import random
import shutil
import struct
import tempfile
import unittest

import silenttestrunner

from remotefilelog.historypack import historypack, mutablehistorypack
from remotefilelog.historypack import historypackstore, historygc

from mercurial import util
from mercurial.node import hex, bin, nullid

class histpacktests(unittest.TestCase):
    def setUp(self):
        self.tempdirs = []

    def tearDown(self):
        for d in self.tempdirs:
            shutil.rmtree(d)

    def makeTempDir(self):
        tempdir = tempfile.mkdtemp()
        self.tempdirs.append(tempdir)
        return tempdir

    def getHash(self, content):
        return util.sha1(content).digest()

    def getFakeHash(self):
        return ''.join(chr(random.randint(0, 255)) for _ in range(20))

    def createPack(self, revisions=None):
        """Creates and returns a historypack containing the specified revisions.

        `revisions` is a list of tuples, where each tuple contains a filanem,
        node, p1node, p2node, and linknode.
        """
        if revisions is None:
            revisions = [("filename", self.getFakeHash(), nullid, nullid,
                          self.getFakeHash())]

        packdir = self.makeTempDir()
        packer = mutablehistorypack(packdir)

        for filename, node, p1, p2, linknode in revisions:
            packer.add(filename, node, p1, p2, linknode)

        path = packer.close()
        return historypack(path)

    def testAddSingle(self):
        """Test putting a single entry into a pack and reading it out.
        """
        filename = "foo"
        node = self.getFakeHash()
        p1 = self.getFakeHash()
        p2 = self.getFakeHash()
        linknode = self.getFakeHash()

        revisions = [(filename, node, p1, p2, linknode)]
        pack = self.createPack(revisions)

        actualp1, actualp2 = pack.getparents(filename, node)
        self.assertEquals(p1, actualp1)
        self.assertEquals(p2, actualp2)

        actuallinknode = pack.getlinknode(filename, node)
        self.assertEquals(linknode, actuallinknode)

    def testAddMultiple(self):
        """Test putting multiple unrelated revisions into a pack and reading
        them out.
        """
        revisions = []
        for i in range(10):
            filename = "foo-%s" % i
            node = self.getFakeHash()
            p1 = self.getFakeHash()
            p2 = self.getFakeHash()
            linknode = self.getFakeHash()
            revisions.append((filename, node, p1, p2, linknode))

        pack = self.createPack(revisions)

        for filename, node, p1, p2, linknode in revisions:
            actualp1, actualp2 = pack.getparents(filename, node)
            self.assertEquals(p1, actualp1)
            self.assertEquals(p2, actualp2)

            actuallinknode = pack.getlinknode(filename, node)
            self.assertEquals(linknode, actuallinknode)

    def testAddAncestorChain(self):
        """Test putting multiple revisions in into a pack and read the ancestor
        chain.
        """
        revisions = []
        filename = "foo"
        lastnode = nullid
        for i in range(10):
            node = self.getFakeHash()
            revisions.append((filename, node, lastnode, nullid, nullid))
            lastnode = node

        # revisions must be added in topological order, newest first
        revisions = list(reversed(revisions))
        pack = self.createPack(revisions)

        # Test that the chain has all the entries
        ancestors = pack.getancestors(revisions[0][0], revisions[0][1])
        for filename, node, p1, p2, linknode in revisions:
            ap1, ap2, alinknode, copyfrom = ancestors[node]
            self.assertEquals(ap1, p1)
            self.assertEquals(ap2, p2)
            self.assertEquals(alinknode, linknode)
            self.assertTrue(copyfrom is None)

    def testPackMany(self):
        """Pack many related and unrelated ancestors.
        """
        # Build a random pack file
        allentries = {}
        ancestorcounts = {}
        revisions = []
        random.seed(0)
        for i in range(100):
            filename = "filename-%s" % i
            entries = []
            p2 = nullid
            linknode = nullid
            for j in range(random.randint(1, 100)):
                node = self.getFakeHash()
                p1 = nullid
                if len(entries) > 0:
                    p1 = entries[random.randint(0, len(entries) - 1)]
                entries.append(node)
                revisions.append((filename, node, p1, p2, linknode))
                allentries[(filename, node)] = (p1, p2, linknode)
                if p1 == nullid:
                    ancestorcounts[(filename, node)] = 1
                else:
                    newcount = ancestorcounts[(filename, p1)] + 1
                    ancestorcounts[(filename, node)] = newcount

        # Must add file entries in reverse topological order
        revisions = list(reversed(revisions))
        pack = self.createPack(revisions)

        # Verify the pack contents
        for (filename, node), (p1, p2, lastnode) in allentries.iteritems():
            ancestors = pack.getancestors(filename, node)
            self.assertEquals(ancestorcounts[(filename, node)],
                              len(ancestors))
            for anode, (ap1, ap2, alinknode, copyfrom) in ancestors.iteritems():
                ep1, ep2, elinknode = allentries[(filename, anode)]
                self.assertEquals(ap1, ep1)
                self.assertEquals(ap2, ep2)
                self.assertEquals(alinknode, elinknode)
                self.assertEquals(copyfrom, None)

    def testGetMissing(self):
        """Test the getmissing() api.
        """
        revisions = []
        filename = "foo"
        for i in range(10):
            node = self.getFakeHash()
            p1 = self.getFakeHash()
            p2 = self.getFakeHash()
            linknode = self.getFakeHash()
            revisions.append((filename, node, p1, p2, linknode))

        pack = self.createPack(revisions)

        missing = pack.getmissing([(filename, revisions[0][1])])
        self.assertFalse(missing)

        missing = pack.getmissing([(filename, revisions[0][1]),
                                   (filename, revisions[1][1])])
        self.assertFalse(missing)

        fakenode = self.getFakeHash()
        missing = pack.getmissing([(filename, revisions[0][1]),
                                   (filename, fakenode)])
        self.assertEquals(missing, [(filename, fakenode)])

    def testAddThrows(self):
        pack = self.createPack()

        try:
            pack.add('filename', nullid, nullid, nullid, nullid)
            self.assertTrue(False, "historypack.add should throw")
        except RuntimeError:
            pass

    def testBadVersionThrows(self):
        pack = self.createPack()
        path = pack.path + '.histpack'
        with open(path) as f:
            raw = f.read()
        raw = struct.pack('!B', 1) + raw[1:]
        with open(path, 'w+') as f:
            f.write(raw)

        try:
            pack = historypack(pack.path)
            self.assertTrue(False, "bad version number should have thrown")
        except RuntimeError:
            pass

# TODO:
# histpack store:
# - getmissing
# - repack two packs into one

if __name__ == '__main__':
    silenttestrunner.main(__name__)
