"""
Simple database for searching a collectoin of audio files.
Can scan for changes to the files at startup (and will update accordingly)
Won't detect new files unless you tell it to rescan a path.
Is smart enough to recognise an iTunes music library and parses the iTunes
database plist file instead of scanning the whole directory structure.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""
import datetime
import plistlib
import unicodedata
import hashlib
import urllib.parse
import urllib.request
import sqlite3
import os
import math
import tinytag
import appdirs
from tqdm import tqdm


__all__ = ["MusicFileDatabase", "Track"]


class MusicFileDatabase:
    def __init__(self, dbfile=None, scan_changes=True, silent=False):
        if not dbfile:
            dblocation = appdirs.user_data_dir("PythonJukebox", "Razorvine")
            os.makedirs(dblocation, mode=0o700, exist_ok=True)
            dbfile = os.path.join(dblocation, "tracks.sqlite")
        dbfile = os.path.abspath(dbfile)
        self.dbfile = dbfile
        self.dbconn = sqlite3.connect(dbfile, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        self.dbconn.row_factory = sqlite3.Row   # make sure we can get results by column name
        self.dbconn.execute("PRAGMA foreign_keys=ON")
        try:
            self.dbconn.execute("SELECT COUNT(*) FROM tracks").fetchone()
            if not silent:
                print("Connected to database.")
                print("Database file:", dbfile)
            if scan_changes:
                self.scan_changes()
        except sqlite3.OperationalError:
            # the table does not yet exist, create the schema
            if not silent:
                print("Creating new database.")
                print("Database file:", dbfile)
            self.dbconn.execute("""CREATE TABLE tracks
                (
                    id integer PRIMARY KEY,
                    title nvarchar(260),
                    artist nvarchar(260),
                    album nvarchar(260),
                    year int,
                    genre nvarchar(100),
                    duration real NOT NULL,
                    modified timestamp NOT NULL,
                    location nvarchar(500) NOT NULL,
                    hash char(40) NOT NULL UNIQUE
                );""")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.dbconn.commit()
        self.dbconn.close()

    def query(self, title=None, artist=None, album=None, year=None, genre=None, result_limit=200):
        sql = "SELECT id, title, artist, album, year, genre, duration, modified, location FROM tracks WHERE "
        where = []
        params = []
        if title:
            where.append("title LIKE ?")
            params.append("%" + title + "%")
        if artist:
            where.append("artist LIKE ?")
            params.append("%" + artist + "%")
        if album:
            where.append("album LIKE ?")
            params.append("%" + album + "%")
        if year:
            where.append("year=?")
            params.append(year)
        if genre:
            where.append("genre LIKE ?")
            params.append("%" + genre + "%")
        if not where:
            raise ValueError("must supply at least one filter parameter")
        sql += "AND ".join(where)
        sql += " ORDER BY artist, title  LIMIT "+str(result_limit)
        result = []
        for track in self.dbconn.execute(sql, params).fetchall():
            result.append(Track(track["id"], track["title"], track["artist"], track["album"], track["year"],
                                track["genre"], track["duration"], track["modified"], track["location"]))
        return result

    def num_tracks(self):
        return self.dbconn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]

    def total_playtime(self):
        result = self.dbconn.execute("SELECT SUM(duration) FROM tracks").fetchone()[0]
        secs = math.ceil(result) if result else 0
        return datetime.timedelta(seconds=secs)

    def get_track(self, hashcode=None, track_id=None):
        if track_id:
            track = self.dbconn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
        elif hashcode:
            track = self.dbconn.execute("SELECT * FROM tracks WHERE hash=?", (hashcode,)).fetchone()
        else:
            raise ValueError("missing search parameter")
        if track:
            return Track(track["id"], track["title"], track["artist"], track["album"], track["year"],
                         track["genre"], track["duration"], track["modified"], track["location"])
        else:
            raise LookupError("track not found")

    def update_path(self, path):
        """
        Adds all recognised music files in the given path.
        If the path points to an iTunes library (containing 'iTunes Library.xml' or 'iTunes Music Library.xml'
        it will read the iTunes library index file instead and skips scanning all files.
        It will only add files that are not present already in the database.
        """
        if not path:
            raise ValueError("must give a path")
        path = os.path.abspath(os.path.normpath(path))
        if os.path.isfile(os.path.join(path, "iTunes Music Library.xml")) or os.path.isfile(os.path.join(path, "iTunes Library.xml")):
            self._add_itunes_library(path)
        else:
            self._scan_path(path)

    def _add_itunes_library(self, path):
        """
        Read the iTunes music library index xml from the given path and use all songs in there
        instead of scanning all files in the given path.
        """
        print("Importing iTunes music library.")
        itunes_idx = os.path.join(path, "iTunes Music Library.xml")
        if not os.path.isfile(itunes_idx):
            itunes_idx = os.path.join(path, "iTunes Library.xml")
        with open(itunes_idx, "rb") as fp:
            library = plistlib.load(fp)
            tracks = library["Tracks"]
            print("iTunes library contains {:d} entries.".format(len(tracks)))
            music_folder = urllib.request.url2pathname(urllib.parse.urlparse(library["Music Folder"]).path)
            if music_folder.endswith(('/', '\\')):
                music_folder = music_folder[:-1]
            music_folder = os.path.split(music_folder)[0] + os.path.sep
        tracks = (Track.from_itunes(t, music_folder, path)
                  for t in tracks.values()
                  if t["Track Type"] == "File" and not t.get("Podcast") and
                  t.get("Genre", "").lower() not in ("audio book", "audiobook") and
                  "document" not in t.get("Kind", ""))
        amount_new = self.add_tracks(tracks)
        print("Added {:d} new tracks.".format(amount_new))

    def _scan_path(self, path):
        print("Scanning for new music files.")
        existing = self.dbconn.execute("SELECT id, modified, location FROM tracks WHERE location LIKE ?", (path + "%",)).fetchall()
        existing = {location: modified for track_id, modified, location in existing}
        print("{:d} tracks already known in the scanned location.".format(len(existing)))
        all_paths = []
        for root, dirs, files in os.walk(path):
            for dirname in dirs:
                path = os.path.join(root, dirname)
                if os.path.isdir(path):
                    all_paths.append(path)
        num_new_songs = 0
        for path in tqdm(all_paths):
            new_songs = []
            try:
                for _, dirs, files in os.walk(path, topdown=True):
                    dirs.clear()
                    for file in files:
                        if file.endswith((".mp3", ".oga", ".ogg", ".opus", ".wav", ".flac", ".wma", ".m4a", ".mp4")):
                            file = os.path.join(path, file)
                            if file in existing:
                                modified = Track.getmtime(file)
                                if modified == existing[file]:
                                    # timestamp is the same, skip re-importing this file
                                    continue
                            tag = self.get_tag(file)
                            if tag.genre and tag.genre.lower() in ("audio book", "audiobook"):
                                continue
                            new_songs.append(Track.from_tag(tag, file))
            except PermissionError as x:
                print("Can't read a path, skipping:", x)
            if new_songs:
                num_new_songs += self.add_tracks(new_songs)
        print("Added {:d} new tracks.".format(num_new_songs))

    def add_tracks(self, tracks):
        before = self.dbconn.execute("SELECT count(*) FROM tracks").fetchone()[0]
        cursor = self.dbconn.cursor()
        for t in tracks:
            try:
                cursor.execute("INSERT INTO tracks(title, artist, album, year, genre, duration, modified, location, hash) VALUES (?,?,?,?,?,?,?,?,?)",
                               (t.title, t.artist, t.album, t.year, t.genre, t.duration, t.modified, t.location, t.hash))
            except sqlite3.IntegrityError as x:
                if str(x) == "UNIQUE constraint failed: tracks.hash":
                    # track already exists with this hash, but update its modification time
                    cursor.execute("UPDATE tracks SET modified=?, year=9999 WHERE hash=?", (t.modified, t.hash))
                else:
                    raise
        after = self.dbconn.execute("SELECT count(*) FROM tracks").fetchone()[0]
        cursor.close()
        self.dbconn.commit()
        amount_new = after - before
        return amount_new

    def get_tag(self, filename):
        try:
            return tinytag.TinyTag.get(filename)
        except tinytag.TinyTagException as x:
            print("Tag error:", x)
            print("Occurred when processing file: ", filename.location.encode("ascii", errors="replace"))
            return tinytag.TinyTag.get(filename, duration=False)

    def scan_changes(self):
        print("Scanning for file changes.")
        changed = []
        removed = []
        tracks = self.dbconn.execute("SELECT id, modified, location FROM tracks").fetchall()
        for track_id, modified, location in tqdm(tracks):
            try:
                file_modified = Track.getmtime(location)
                if file_modified != modified:
                    changed.append((track_id, location))
            except FileNotFoundError:
                removed.append(track_id)
        print("{:d} changes and {:d} removals detected.".format(len(changed), len(removed)))
        if changed or removed:
            print("Updating track information.")
            if changed:
                new_songs = []
                for track_id, location in tqdm(changed):
                    tag = self.get_tag(location)
                    new_songs.append(Track.from_tag(tag, location))
                    self.dbconn.execute("DELETE FROM tracks WHERE id=?", (track_id,))
                self.add_tracks(new_songs)
            for track_id in removed:
                self.dbconn.execute("DELETE FROM tracks WHERE id=?", (track_id,))


class Track:
    def __init__(self, trackid, title, artist, album, year, genre, duration, modified, location):
        self.id = trackid
        self.title = title
        self.artist = artist
        self.album = album
        self.year = year
        self.genre = genre
        self.duration = math.ceil(duration)
        self.modified = modified
        self.location = location

    @property
    def hash(self):
        return hashlib.sha1("{}:{}:{}:{}".format(self.title, self.artist, self.album, self.location).encode("utf-8")).hexdigest()

    def __hash__(self):
        return self.hash

    def __repr__(self):
        return "<Track at 0x{:x}; trackid={:d} title={} artist={} album={}>".format(id(self), self.id, self.title, self.artist, self.album)

    @classmethod
    def from_itunes(cls, itunes_track, itunes_music_folder, real_music_folder):
        title = itunes_track.get("Name", None)
        artist = itunes_track.get("Artist", None)
        album = itunes_track.get("Album", None)
        year = itunes_track.get("Year", None)
        genre = itunes_track.get("Genre", None)
        duration = itunes_track["Total Time"] / 1000.0
        modified = itunes_track["Date Modified"]
        location = urllib.request.url2pathname(urllib.parse.urlparse(itunes_track["Location"]).path)
        location = os.path.join(real_music_folder, location[len(itunes_music_folder):])
        if not title:
            title = os.path.splitext(os.path.basename(location))[0]
        # normalize unicode strings to avoid problems with composite characters
        if title:
            title = unicodedata.normalize("NFC", title)
        if artist:
            artist = unicodedata.normalize("NFC", artist)
        if album:
            album = unicodedata.normalize("NFC", album)
        if genre:
            genre = unicodedata.normalize("NFC", genre)
        if location:
            location = unicodedata.normalize("NFC", location)
        return cls(None, title, artist, album, year, genre, duration, modified, location)

    @staticmethod
    def getmtime(filename):
        return datetime.datetime.utcfromtimestamp(os.path.getmtime(filename))

    @classmethod
    def from_tag(cls, tag, location):
        modified = Track.getmtime(location)
        year = tag.year or None
        if year:
            if len(str(year)) > 4:
                year = str(year)[:4]
            year = int(year)
        title = tag.title
        if not title:
            title = os.path.splitext(os.path.basename(location))[0]
        return cls(None, title, tag.artist, tag.album, year, tag.genre, tag.duration, modified, location)
