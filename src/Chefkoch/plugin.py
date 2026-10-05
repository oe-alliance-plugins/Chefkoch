# PYTHON IMPORTS
from base64 import b64decode
from datetime import datetime
from operator import itemgetter
from os import rename, remove, makedirs, linesep
from os.path import join, exists
from secrets import randbelow, choice
from requests import get, exceptions
from PIL import Image
from smtplib import SMTP, SMTP_SSL, SMTPAuthenticationError, SMTPConnectError, SMTPException
from shutil import copy
from ssl import create_default_context
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from time import strftime
from twisted.internet.reactor import callInThread

# ENIGMA IMPORTS
from enigma import eListboxPythonMultiContent, eServiceReference, eTimer, getDesktop, gFont, loadPNG, RT_HALIGN_LEFT, RT_HALIGN_CENTER, RT_VALIGN_CENTER, RT_WRAP
from Components.ActionMap import ActionMap, NumberActionMap
from Components.config import config, ConfigSubsection, ConfigInteger, ConfigPassword, ConfigSelection, ConfigText, ConfigYesNo
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Components.ProgressBar import ProgressBar
from Plugins.Plugin import PluginDescriptor
from Screens.ChannelSelection import ChannelSelection
from Screens.ChoiceBox import ChoiceBox
from Screens.InfoBar import MoviePlayer
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Setup import Setup
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.Directories import fileExists, resolveFilename, SCOPE_PLUGINS, SCOPE_CONFIG

# PLUGIN IMPORTS
from . import __version__

# orderBy-Codes: 0= unbekannt, 1= = unbekannt, 2= unbekannt, 3= rating, 4= unbekannt, 5= unbekannt, 6= createdAt, 7= isPremium, 8= unbekannt
# nicht unterstüzte orderBy-Queries: numVotes, preparationTime
config.plugins.chefkoch = ConfigSubsection()
config.plugins.chefkoch.bigfontsize = ConfigYesNo(default=False)
config.plugins.chefkoch.maxrecipes = ConfigSelection(default=100, choices=[10, 20, 50, 100, 200, 500, 1000])
config.plugins.chefkoch.maxcomments = ConfigSelection(default=100, choices=[10, 20, 50, 100, 200, 500])
config.plugins.chefkoch.maxpictures = ConfigSelection(default=20, choices=[10, 20, 50, 100])
config.plugins.chefkoch.mail = ConfigYesNo(default=False)
config.plugins.chefkoch.mailfrom = ConfigText(default="", fixed_size=False)
config.plugins.chefkoch.mailto = ConfigText(default="", fixed_size=False)
config.plugins.chefkoch.login = ConfigText(default="", fixed_size=False)
config.plugins.chefkoch.password = ConfigPassword(default="", fixed_size=False)
config.plugins.chefkoch.server = ConfigText(default="", fixed_size=False)
config.plugins.chefkoch.port = ConfigInteger(587, (0, 99999))
config.plugins.chefkoch.starttls = ConfigYesNo(default=True)
config.plugins.chefkoch.debuglog = ConfigYesNo(default=False)
config.plugins.chefkoch.logtofile = ConfigYesNo(default=False)

hideflag = False


class CKglobals:
	agent = choice([
			"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.10 Safari/605.1.1",
			"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.3,"
			"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
			"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.",
			"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
			"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.",
			"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 OPR/117.0.0."
			])
	module_name = __name__.split(".")[-2]
	release = f"v{__version__}"
	base_url = "https://www.chefkoch.de"
	lines_per_page = 8
	hideflag = False
	pic_file: str = "/tmp/chefkoch.jpg"
	pic_url_base = bytes.fromhex("68747470733A2F2F696D672E636865666B6F63682D63646E2E64652F72657A657074652FF"[:-1]).decode()
	api_url_base = bytes.fromhex("68747470733A2F2F6170692E636865666B6F63682E64652F76322FA"[:-1]).decode()
	no_pic_url = bytes.fromhex("68747470733A2F2F696D672E636865666B6F63682D63646E2E64652F696D672F64656661756C742F6C61796F75742F7265636970652D6E6F706963747572652E6A70670"[:-1]).decode()
	alpha = "/proc/stb/video/ckglobals.ALPHA" if fileExists("/proc/stb/video/ckglobals.ALPHA") else None
	plugin_path = resolveFilename(SCOPE_PLUGINS, "Extensions/Chefkoch/")  # e.g. /usr/lib/enigma2/python/Plugins/Extensions/Chefkoch/
	config_path = resolveFilename(SCOPE_CONFIG, "Chefkoch/")  # e.g. /etc/enigma2/Chefkoch/
	pic_path = join(plugin_path, "pic/")
	vkat_db = join(config_path, "VKATdb")
	favorites = join(config_path, "favoriten")
	searches = join(config_path, "suchen")
	resolution = "FHD" if getDesktop(0).size().width() >= 1920 else "HD"
	scale = 1.5 if resolution == "FHD" else 1.0


ckglobals = CKglobals


class AllScreen(Screen):
	def prepare_paths(self):
		try:
			if not exists(ckglobals.config_path):
				makedirs(ckglobals.config_path)
			source = join(ckglobals.plugin_path, "db/", "VKATdb")
			if not exists(ckglobals.vkat_db) and exists(source):
				copy(source, ckglobals.vkat_db)
			for filename in ["favoriten", "suchen"]:  # DEPRECATED: frühere Versionen legten diese Dateien im Plugin-Ordner ab
				source = join(ckglobals.plugin_path, "db/", filename)
				destination = join(ckglobals.config_path, filename)
				if not exists(destination) and exists(source):
					copy(source, destination)  # kopiere Datei aus früherem Ordner (falsch) in den Config-Ordner (richtig)
					remove(source)  # lösche an alter (falscher) Stelle
		except OSError as err:
			self.ck_log(f"[{ckglobals.module_name}] Error preparing paths: {str(err)}")

	def get_api_data(self, apiurl, params={}):
		url = f"{ckglobals.api_url_base}{apiurl}"
		headers = {"User-Agent": ckglobals.agent, "Accept": "application/json"}
		try:
			response = get(url=url, params=params, headers=headers, timeout=(3.05, 6))
			response.raise_for_status()
			return (response.json(), response.status_code)
		except exceptions.RequestException as error:
			return ({}, error)

	def ck_log(self, info, wert="", debug=False):
		if debug and not config.plugins.chefkoch.debuglog.value:
			return
		if config.plugins.chefkoch.logtofile.value:
			try:
				with open("/home/root/logs/chefkoch.log", "a") as f:
					f.write(f"{strftime('%H:%M:%S')} {info} {wert}\r\n")
			except OSError as err:
				print(f"[{ckglobals.module_name}] Error writing Logfile: {str(err)}")
		else:
			print(f"[{ckglobals.module_name}] {str(info)} {str(wert)}")

	def hide_screen(self):
		global hideflag
		if ckglobals.alpha and hideflag:
			hideflag = False
			for index in range(40, -1, -1):
				with open(ckglobals.alpha, "w") as f:
					f.write(f"{int(config.av.osd_ckglobals.ALPHA.value * index / 40):d}")
		elif ckglobals.alpha:
			hideflag = True
			for index in range(41):
				with open(ckglobals.alpha, "w") as f:
					f.write(f"{int(config.av.osd_ckglobals.ALPHA.value * index / 40):d}")

	def pic_download(self, url, index=None):
		headers = {"User-Agent": ckglobals.agent, "Accept": "application/json"}
		try:
			response = get(url, headers=headers, timeout=(3.05, 6))
			response.raise_for_status()
		except exceptions.RequestException as error:
			self.download_error(error)
		else:
			picfile = ckglobals.pic_file if index is None else f"/tmp/chefkoch{index}.jpg"
			try:
				with open(picfile, "wb") as f:
					f.write(response.content)
			except OSError as logerr:
				self.ck_log(f"Error writing picture '{picfile}': {str(logerr)}")
			else:
				if index is None:
					self.show_pic()
				else:
					self[f"pic{index}"].instance.setPixmapFromFile(picfile)
					self[f"pic{index}"].show()

	def show_pic(self):
		if exists(ckglobals.pic_file):
			self["picture"].instance.setPixmapFromFile(ckglobals.pic_file)
			self["picture"].show()

	def download_error(self, error):
		self.ck_log(error)


class CKview(AllScreen):
	skin = """
		<screen name="CKview" position="center,center" size="1280,720" resolution="1280,720" title="lade Daten, bitte warten..." flags="wfNoBorder" backgroundColor="background">
			<widget source="Title" render="Label" position="center,0" size="870,60" font="Regular; 24" transparent="1" foregroundColor="#336f3d" backgroundColor="white" halign="center" valign="center" zPosition="3" />
			<ePixmap position="0,0" size="1280,60" pixmap="{picpath}/chefkoch.png" alphatest="blend" zPosition="1" />
			<ePixmap position="0,0" size="1920,1080" pixmap="{picpath}/background.png"  zPosition="-10" />
			<widget render="Label" source="global.CurrentTime" position="1112,0" size="120,30" font="Regular;26" foregroundColor="#697279" backgroundColor="white" halign="center" valign="center" zPosition="2">
				<convert type="ClockToText">Format:%H:%M:%S</convert>
			</widget>
			<widget name="release" position="43,25" size="40,19" font="Regular; 14" foregroundColor="#697279" backgroundColor="white" halign="left" valign="center" transparent="1" zPosition="2" />
			<widget name="menu" position="40,75" size="1065,600" font="Regular;{fontsize}" selectionPixmap="{picpath}/BG_Pixmap_Menu.png" foregroundColor="white" backgroundColor="black"  scrollbarMode="showAlways" scrollbarBorderWidth="1" scrollbarWidth="10" scrollbarForegroundColor="#b5d7bb" scrollbarBorderColor="#336F3D" zPosition="1" transparent="1"/>
			<widget name="vid0" position="1146,88" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="vid1" position="1146,163" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="vid2" position="1146,238" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="vid3" position="1146,313" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="vid4" position="1146,388" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="vid5" position="1146,463" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="vid6" position="1146,538" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="vid7" position="1146,613" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="pic0" position="1115,75" size="113,75" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="pic1" position="1115,150" size="113,75" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="pic2" position="1115,225" size="113,75" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="pic3" position="1115,300" size="113,75" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="pic4" position="1115,375" size="113,75" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="pic5" position="1115,450" size="113,75" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="pic6" position="1115,525" size="113,75" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="pic7" position="1115,600" size="113,75" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="picture" position="center,70" size="280,210" scaleFlags="centerScaled" zPosition="1" />
			<widget name="postvid" position="center,145" size="50,50" pixmap="{picpath}/videoicon.png" alphatest="blend" zPosition="1" />
			<widget name="starsbg" position="53,75" size="228,40" pixmap="{picpath}/starsbar_empty.png" transparent="1" zPosition="0" alphatest="blend" />
			<widget name="stars" position="53,75" size="228,40" pixmap="{picpath}/starsbar_filled.png" transparent="1" />
			<widget name="scoretext" position="53,130" size="440,130" font="Regular; 20" halign="left" zPosition="1" transparent="1" />
			<widget name="recipetext" position="790,70" size="438,190" font="Regular; 20" halign="left" zPosition="1" transparent="1" />
			<widget name="textpage" position="50,300" size="1178,375" font="Regular;{fontsize}" scrollbarMode="showOnDemand" scrollbarBorderWidth="2" scrollbarWidth="10" scrollbarForegroundColor="#b5d7bb" scrollbarBorderColor="#336F3D" halign="left" zPosition="0" transparent="1" />
			<widget name="pageinfo" position="1112,36" size="120,21" font="Regular; 16" foregroundColor="white" backgroundColor="#336f3d" halign="center" transparent="0" zPosition="2" />
			<widget name="label_red" position="25,690" size="180,24" font="Regular;18" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="2" />
			<widget name="label_green" position="235,690" size="300,24" font="Regular;18" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="2" />
			<widget name="label_yellow" position="565,690" size="240,24" font="Regular;18" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="2" />
			<widget name="label_blue" position="835,690" size="150,24" font="Regular;18" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="2" />
			<widget name="label_rezeptnr" position="center,41" size="870,20" font="Regular; 14" foregroundColor="#697279" backgroundColor="white" halign="center" valign="center" transparent="1" zPosition="2" />
			<widget name="label_1-0" position="86,254" size="350,27" font="Regular; 20" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="1" />
			<widget name="button_1-0" position="49,252" size="30,30" pixmap="{picpath}/1-0.png" alphatest="blend" zPosition="1" />
			<widget name="label_ok" position="1030,690" size="180,24" font="Regular;18" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="2" />
			<widget name="button_ok" position="992,686" size="30,30" pixmap="{picpath}/ok.png" alphatest="blend" zPosition="1" />
			<widget name="label_play" position="833,255" size="240,24" font="Regular;18" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="2" />
			<widget name="button_play" position="794,252" size="30,30" pixmap="{picpath}/play.png" alphatest="blend" zPosition="1" />
			<widget name="button_green" position="331,740" size="18,18" zPosition="2" />
			<widget name="button_yellow" position="714,740" size="18,18" zPosition="2" />
			<widget name="button_red" position="30,740" size="18,18" alphatest="blend" zPosition="2" />
			<widget name="button_blue" position="1091,740" size="18,18" alphatest="blend" zPosition="2" />
			<eLabel name="button_red" position="5,687" size="8,30" backgroundColor="red" zPosition="2" />
			<eLabel name="button_green" position="215,687" size="8,30" backgroundColor="green" zPosition="2" />
			<eLabel name="button_yellow" position="545,687" size="8,30" backgroundColor="yellow" zPosition="2" />
			<eLabel name="button_blue" position="815,687" size="8,30" backgroundColor="blue" zPosition="2" />
			<eLabel name="Line_Bottom" position="0,680" size="1280,1" backgroundColor="#3B8047" zPosition="5" />
			<widget name="Line_Bottom" position="50,290" size="1178,1" backgroundColor="#3B8047" zPosition="0" />
		</screen>"""

	def __init__(self, session, query, titel, sort, fav, zufall):
		global hideflag
		hideflag = True
		fontsize = int((18 if config.plugins.chefkoch.bigfontsize.value else 16) * ckglobals.scale)
		self.skin = self.skin.replace("{picpath}", f"{ckglobals.plugin_path}/pic/{ckglobals.resolution}").replace("{fontsize}", str(fontsize))
		Screen.__init__(self, session, self.skin)
		self.session = session
		self.query = query
		self.titel = titel
		self.sort = sort
		self.fav = fav
		self.zufall = zufall
		self.rezept = f"{ckglobals.base_url}/rezepte/"
		self.rezeptfile = "/tmp/Rezept.html"
		self.comment = False
		self.len = 0
		self.count = 0
		self.max_page = 0
		self.curr_item = 0
		self.pic_count = 0
		self.video_count = 0
		self.current = "menu"
		self.name = ""
		self.chefvideo = ""
		self.grp_s = []
		self.rez = {}
		self.kom = {}
		self.picurllist = []
		self.titellist = []
		self.videolist = []
		self.rezeptelist = []
		self.rezeptelinks = []
		self.sortname = ["{keine}", "Anzahl Bewertungen", "Anzahl Sterne", "mit Video", "Erstelldatum"]
		for index in range(ckglobals.lines_per_page):
			self[f"pic{index}"] = Pixmap()
			self[f"vid{index}"] = Pixmap()
		self["picture"] = Pixmap()
		self["postvid"] = Pixmap()
		self["stars"] = ProgressBar()
		self["starsbg"] = Pixmap()
		self["scoretext"] = Label("")
		self["recipetext"] = Label("")
		self["button_green"] = Pixmap()
		self["button_red"] = Pixmap()
		self["button_yellow"] = Pixmap()
		self["button_blue"] = Pixmap()
		self["textpage"] = ScrollLabel("")
		self["menu"] = ItemList([])
		self["label_red"] = Label("")
		self["label_green"] = Label("")
		self["label_yellow"] = Label("")
		self["label_blue"] = Label("")
		self["label_rezeptnr"] = Label("")
		self["label_1-0"] = Label("")
		self["button_1-0"] = Pixmap()
		self["pageinfo"] = Label("")
		self["label_ok"] = Label("")
		self["button_ok"] = Pixmap()
		self["label_play"] = Label("")
		self["button_play"] = Pixmap()
		self["Line_Bottom"] = Label("")
		self["release"] = Label(ckglobals.release)
		self["NumberActions"] = NumberActionMap(["NumberActions", "OkCancelActions", "DirectionActions", "ColorActions", "ChannelSelectBaseActions", "ButtonSetupActions"], {
			"ok": self.ok,
			"cancel": self.exit,
			"play": self.play_video,
			"playpause": self.play_video,
			"right": self.next_page,
			"left": self.prev_page,
			"down": self.down,
			"up": self.up,
			"nextBouquet": self.next_page,
			"prevBouquet": self.prev_page,
			"red": self.red,
			"yellow": self.yellow,
			"green": self.green,
			"blue": self.hide_screen,
			"0": self.goto_page,
			"1": self.goto_page,
			"2": self.goto_page,
			"3": self.goto_page,
			"4": self.goto_page,
			"5": self.goto_page,
			"6": self.goto_page,
			"7": self.goto_page,
			"8": self.goto_page,
			"9": self.goto_page,
		}, -1)
		self.onLayoutFinish.append(self.on_layout_finished)

	def on_layout_finished(self):
		if self.zufall:
			self.current = "postview"
			if not self.grp_s:
				self.grp_s = self.get_grps()
				self.max_page = (len(self.grp_s) - 1) // ckglobals.lines_per_page + 1
			self.show_recipe(self.grp_s[randbelow(len(self.grp_s))].get("id", ""))
			callInThread(self.fill_recipe)
		elif self.fav:
			self.current = "postview"
			self.show_recipe(self.query)
			callInThread(self.fill_recipe)
		else:
			self.current = "menu"
			self.show_rlist()
			callInThread(self.fill_rlist)

	def show_rlist(self):  # zeige leere Rezeptliste
		for index in range(ckglobals.lines_per_page):
			self[f"pic{index}"].hide()
			self[f"vid{index}"].hide()
		self["postvid"].hide()
		self["Line_Bottom"].hide()
		self["starsbg"].hide()
		self["stars"].hide()
		self["button_green"].hide()
		self["button_yellow"].hide()
		self["button_red"].show()
		self["button_blue"].show()
		self["label_red"].setText("Rezept zu Favoriten")
		self["label_green"].setText("")
		self["label_yellow"].setText("Suche")
		self["label_blue"].setText("Ein-/Ausblenden")
		self["label_rezeptnr"].setText(f"Rezept Nr. {self.curr_item + 1}")
		self["label_ok"].setText("zum Rezept")
		self["label_ok"].show()
		self["label_1-0"].setText("")
		self["button_1-0"].hide()
		self["button_ok"].show()
		self["button_play"].hide()
		self["label_play"].hide()
		self["scoretext"].hide()
		self["recipetext"].hide()
		self["textpage"].hide()
		self["picture"].hide()
		self["pageinfo"].show()
		self["menu"].show()

	def fill_rlist(self):  # fülle die Rezeptliste
		self.grp_s = GRPs = self.get_grps()
		lenGRPs = len(GRPs)
		self.max_page = (lenGRPs - 1) // ckglobals.lines_per_page + 1
		self.setTitle(f"{lenGRPs} {self.titel.replace(' Rezepte', '')} ({self.video_count} {'Video' if self.video_count == 1 else 'Videos'})")
		self["label_green"].setText(f"Sortierung: {self.sortname[self.sort]}")
		self["pageinfo"].setText(f"Seite {int(self.curr_item // ckglobals.lines_per_page + 1)} von {self.max_page}")
		kochentries = []
		titellist = []
		videolist = []
		picurllist = []
		for index, group in enumerate(GRPs):
			ident = str(group.get("id", ""))
			titel = group.get("title", "")
			time = str(group.get("preparationTime", ""))
			if group.get("numVotes", ""):
				count = str(group.get("numVotes", ""))
				score = str(round(group.get("rating", "") / 5, 1) * 5).replace(".", "_").replace("_0", "")
			else:
				count = "keine"
				score = "0"
			previewImageId = group.get('previewImageId', '')
			picurl = f"{ckglobals.pic_url_base}{ident}/bilder/{previewImageId}/crop-160x120/{titel.replace(' ', '-')}.jpg" if previewImageId else ckglobals.no_pic_url
			text = group.get("subtitle", "")
			if len(text) > 155:
				text = f"{text[:155]}…"
			titellist.append(titel)
			videolist.append(group.get("hasVideo", ""))
			picurllist.append(picurl)
			res = [index]
			res.append(MultiContentEntryText(pos=(int(110 * ckglobals.scale), 10), size=(int(965 * ckglobals.scale), int(30 * ckglobals.scale)), font=-1, color_sel=16777215, flags=RT_HALIGN_LEFT, text=titel))  # TITLE
			png = join(ckglobals.pic_path, f"{ckglobals.resolution}", f"/small-{score}.png")
			if fileExists(png):
				res.append(MultiContentEntryPixmapAlphaTest(pos=(int(14 * ckglobals.scale), int(36 * ckglobals.scale)), size=(int(75 * ckglobals.scale), int(15 * ckglobals.scale)), png=loadPNG(png)))  # STARS
			res.append(MultiContentEntryText(pos=(int(11 * ckglobals.scale), int(52 * ckglobals.scale)), size=(int(75 * ckglobals.scale), int(30 * ckglobals.scale)), font=1, color=16777215, color_sel=16777215,
											flags=RT_HALIGN_CENTER, text=f"({count})"))  # COUNT
			res.append(MultiContentEntryText(pos=(int(111 * ckglobals.scale), int(45 * ckglobals.scale)), size=(int(965 * ckglobals.scale), int(70 * ckglobals.scale)),
											font=-1, color=10857646, color_sel=13817818, flags=RT_HALIGN_LEFT | RT_WRAP, text=text))  # TEXT
			res.append(MultiContentEntryText(pos=(int(10 * ckglobals.scale), int(6 * ckglobals.scale)), size=(int(75 * ckglobals.scale), int(26 * ckglobals.scale)), font=0, backcolor=3899463,
											color=16777215, backcolor_sel=15704383, color_sel=16777215, flags=RT_HALIGN_CENTER, text=time))  # TIME
			kochentries.append(res)
		self.titellist = titellist
		self.videolist = videolist
		self.picurllist = picurllist
		self.set_prev_icons(0)
		self.len = len(kochentries)
		self["menu"].l.setItemHeight(int(75 * ckglobals.scale))
		self["menu"].l.setList(kochentries)
		self["menu"].moveToIndex(self.curr_item)
		self.curr_item = self["menu"].getSelectedIndex()
		self.set_prev_icons(self.curr_item - self.curr_item % ckglobals.lines_per_page)

	def format_datum(self, date):
		return str(datetime.strptime(date[:10], "%Y-%m-%d").strftime("%d.%m.%Y"))

	def format_datum_zeit(self, date):
		datum = datetime.strptime(date[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
		zeit = datetime.strptime(date[11:19], "%H:%M:%S").strftime("%H:%M")
		return f"vom {datum} um {zeit}"

	def format_username(self, username, rank, trim):
		trim = trim if trim > 0 else 100
		return "Unbekannt" if "unknown" in username else f"{username} ({rank}*)"

	def show_recipe(self, ident):  # zeige leeres Rezept
		self.curr_id = ident
		for index in range(ckglobals.lines_per_page):
			self[f"pic{index}"].hide()
			self[f"vid{index}"].hide()
		self["picture"].hide()
		self["menu"].hide()
		self["button_green"].hide()
		self["button_yellow"].hide()
		self["button_red"].show()
		self["button_blue"].show()
		self["label_green"].setText("Rezept per Email")
		self["label_red"].setText("Rezept zu Favoriten")
		self["label_yellow"].setText("")
		self["label_blue"].setText("Ein-/Ausblenden")
		self["label_rezeptnr"].setText("")
		self["label_1-0"].setText("")
		self["button_1-0"].hide()
		self["pageinfo"].hide()
		self["label_ok"].setText("")
		self["button_ok"].hide()
		self["postvid"].hide()
		self["label_play"].hide()
		self["button_play"].hide()
		self["Line_Bottom"].hide()
		self["textpage"].setText("")
		self["textpage"].show()

	def fill_recipe(self):  # fülle das Rezept
		self.rez = self.get_rez(self.curr_id)
		plaintitel = self.titel.replace("'", "")
		picurl = f"{ckglobals.pic_url_base}{self.curr_id}/bilder/{self.rez.get('previewImageId', '')}/crop-960x720/{plaintitel}.jpg" if self.rez.get("hasImage", "") else ckglobals.no_pic_url
		callInThread(self.pic_download, picurl)
		if self.rez.get("rating", ""):
			score = self.rez.get("rating", "").get("rating", "") * 20.0
			scoretext = f"{self.rez.get('rating', '').get('rating', ''):1.1f} ({self.rez.get('rating', '').get('numVotes', '')} Bewertungen)"
		else:
			score = 0.0
			scoretext = "(ohne Bewertung)"
		preptime = self.rez.get("preparationTime", "")
		cooktime = self.rez.get("cookingTime", "")
		resttime = self.rez.get("restingTime", "")
		totaltime = self.rez.get("totalTime", "")
		self.pic_count = self.rez.get("imageCount", "")
		self.setTitle(str(self.rez.get("title", "")))
		if preptime != 0:
			scoretext += f"\nArbeitszeit\t: {self.get_time_string(preptime)}"
		if cooktime != 0:
			scoretext += f"\nKoch-/Backzeit\t: {self.get_time_string(cooktime)}"
		if resttime != 0:
			scoretext += f"\nRuhezeit\t: {self.get_time_string(resttime)}"
		if totaltime != 0:
			scoretext += f"\nGesamtzeit\t: {self.get_time_string(totaltime)}"
		self["stars"].setValue(score)
		self["stars"].show()
		self["starsbg"].show()
		self["scoretext"].setText(scoretext)
		self["scoretext"].show()
		effort = ["keiner", "simpel", "normal", "pfiffig"]
		recipetext = f"Rezept-Identnr.\t: {self.curr_id}"
		recipetext += f"\nAufwand\t: {effort[self.rez.get('difficulty', '')]}"
		recipetext += f"\nErstellername\t: {self.format_username(self.rez.get('owner', '').get('username', ''), self.rez.get('owner', '').get('rank', ''), 22)}"
		recipetext += f"\nErstelldatum\t: {self.format_datum(self.rez.get('createdAt', ''))}"
		if self.rez.get("nutrition", ""):
			kcalori = self.rez.get("nutrition", "").get("kCalories", "")
			kcalori = f"{kcalori}" if kcalori else "k.A."
			protein = self.rez.get("nutrition", "").get("proteinContent", "")
			protein = f"{protein} g" if protein else "k.A."
			fatcont = self.rez.get("nutrition", "").get("fatContent", "")
			fatcont = f"{fatcont} g" if fatcont else "k.A."
			carbohyd = self.rez.get("nutrition", "").get("carbohydrateContent", "")
			carbohyd = f"{carbohyd} g" if carbohyd else "k.A."
			recipetext += f"\n\n{'kcal':13}{'Eiweiß':13}{'Fett':14}{'Kohlenhydr.':14}"
			recipetext += f"\n{kcalori:13}{protein:13}{protein:12}{carbohyd}"
		self["recipetext"].setText(str(recipetext))
		self["recipetext"].show()
		self["Line_Bottom"].show()
		self.img = self.get_img(self.curr_id)
		if self.pic_count == 1:
			self["label_ok"].setText("Vollbild")
			self["button_ok"].show()
		elif self.pic_count > 1:
			self["label_ok"].setText(f"{self.img_len} Rezeptbilder")
			self["button_ok"].show()
		else:
			self["label_ok"].setText("")
			self["button_ok"].hide()
		self.kom = self.get_kom(self.curr_id)
		if self.current == "postview":
			self.show_rezept()

	def get_rez(self, ident):  # hole den jeweiligen Rezeptdatensatz
		result, resp = self.get_api_data(apiurl=f"recipes/{ident}")
		if resp != 200:
			self.session.openWithCallback(self.eject, MessageBox, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
		return result

	def get_img(self, ident):  # hole die jeweilige Rezeptbilderliste
		result, resp = self.get_api_data(apiurl=f"recipes/{ident}/images", params={"offset": 0, "limit": config.plugins.chefkoch.maxpictures.value})
		img = {}
		if resp == 200:
			self.img_len = int(config.plugins.chefkoch.maxpictures.value) if result.get("count", "") > int(config.plugins.chefkoch.maxpictures.value) else result.get("count", "")
			img["count"] = self.img_len
			img["results"] = result.get("results", "")
		else:
			self.session.openWithCallback(self.eject, MessageBox, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
		return img

	def get_kom(self, ident):  # hole die jeweilige Rezeptkommentarliste
		maxcomments = config.plugins.chefkoch.maxcomments.value
		result, resp = self.get_api_data(apiurl=f"recipes/{ident}/comments", params={"offset": 0, "limit": maxcomments})
		if resp == 200:
			self.kom_len = maxcomments if result.get("count", "") > maxcomments else result.get("count", "")
		else:
			self.session.openWithCallback(self.eject, MessageBox, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
		return result

	def get_grps(self):  # hole die gewünschte Rezeptgruppe (alle Rezepte, davon 'videocount' mit Video)
		limit = config.plugins.chefkoch.maxrecipes.value
		videocount, GRPs = 0, []
		for index in range(max((limit) // 100, 1)):
			result, resp = self.get_api_data(apiurl="recipes", params={"query": self.query, "offset": index * 100, "limit": min(limit, 100)})  # 3= sort by 'rating'
			if resp != 200:
				self.session.openWithCallback(self.eject, MessageBox, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
				self.close()
				return []
			for j in range(len(result.get("results", ""))):
				if result.get("results", "")[j].get("recipe", "").get("isRejected", ""):
					continue
				grp = {}
				grp["id"] = result.get("results", "")[j].get("recipe", "").get("id", "")
				grp["createdAt"] = result.get("results", "")[j].get("recipe", "").get("createdAt", "")
				grp["preparationTime"] = result.get("results", "")[j].get("recipe", "").get("preparationTime", "")
				if result.get("results", "")[j].get("recipe", "").get("rating", ""):
					grp["rating"] = result.get("results", "")[j].get("recipe", "").get("rating", "").get("rating", "")
					grp["numVotes"] = result.get("results", "")[j].get("recipe", "").get("rating", "").get("numVotes", "")
				else:
					grp["rating"] = 0
					grp["numVotes"] = False
				if result.get("results", "")[j].get("recipe", "").get("hasImage", ""):
					grp["previewImageId"] = result.get("results", "")[j].get("recipe", "").get("previewImageId", "")
				else:
					grp["previewImageId"] = False
				grp["hasVideo"] = result.get("results", "")[j].get("recipe", "").get("hasVideo", "")
				titel = str(result.get("results", "")[j].get("recipe", "").get("title", ""))
				grp["title"] = titel
				grp["subtitle"] = str(result.get("results", "")[j].get("recipe", "").get("subtitle", ""))
				if result.get("results", "")[j].get("recipe", "").get("hasVideo", ""):
					videocount += 1
				GRPs.append(grp)
		self.video_count = videocount
		if self.sort == 0:
			return GRPs
		elif self.sort == 1:
			return sorted(GRPs, key=itemgetter("numVotes"), reverse=True)
		elif self.sort == 2:
			return sorted(GRPs, key=itemgetter("rating"), reverse=True)
		elif self.sort == 3:
			return sorted(GRPs, key=itemgetter("hasVideo", "numVotes"), reverse=True)
		elif self.sort == 4:
			return sorted(GRPs, key=itemgetter("createdAt"), reverse=True)
		else:
			return []

	def get_time_string(self, duration):
		days = duration // 1440
		hours = duration // 60
		minutes = duration % 60
		if days == 0:
			daytext = ""
			hourtext = f"ca. {hours} h" if hours != 0 else ""
			minutetext = f"{minutes} min" if minutes != 0 else ""
		else:
			daytext = f"{days} Tage" if days > 1 else "1 Tag"
			hourtext = ""
			minutetext = ""
		ausgabe = f"{daytext} {hourtext} {minutetext}"
		return ausgabe

	def ok(self):
		if hideflag and self.current == "menu":
			self.current = "postview"
			self.curr_item = self["menu"].getSelectedIndex()
			if self.grp_s:
				self.show_recipe(self.grp_s[self.curr_item].get("id", ""))
				callInThread(self.fill_recipe)
		elif hideflag and self.current == "postview" and self.rez and self.pic_count == 1:
			self.session.openWithCallback(self.show_pic, CKfullscreen)
		elif hideflag and self.current == "postview" and self.rez and self.pic_count > 1:
			self.session.open(CKpicshow, self.titel, self.rez, self.img)

	def red(self):
		if self.titellist and self.zufall:
			name = self.name
			self.session.openWithCallback(self.red_return, MessageBox, f"\nRezept '{name}' zu den Favoriten hinzufügen?", MessageBox.TYPE_YESNO, timeout=10, default=True)
		elif self.titellist:
			self.curr_item = self["menu"].getSelectedIndex()
			name = self.titellist[self.curr_item]
			self.session.openWithCallback(self.red_return, MessageBox, f"\nRezept '{name}' zu den Favoriten hinzufügen?", MessageBox.TYPE_YESNO, timeout=10, default=True)

	def red_return(self, answer):
		if answer is True and self.zufall:
			data = f"{self.name}:::{self.grp_s[self.curr_item].get('id', '')}"
			with open(ckglobals.favorites, "a") as f:
				f.write(data)
				f.write(linesep)
			self.session.open(CKfavoriten)
		elif answer is True:
			self.curr_item = self["menu"].getSelectedIndex()
			data = f"{self.titellist[self.curr_item]}:::{self.grp_s[self.curr_item].get('id', '')}"
			with open(ckglobals.favorites, "a") as f:
				f.write(data)
				f.write(linesep)
			self.session.open(CKfavoriten)

	def green(self):
		if self.current == "postview" and self.rez and config.plugins.chefkoch.mail.value:
			mailto = [(index.strip(),) for index in config.plugins.chefkoch.mailto.value.split(",")]
			self.session.openWithCallback(self.green_return, ChoiceBox, title="Rezept an folgende E-Mail Adresse senden:", list=mailto)
		elif self.current == "postview" and self.rez:
			self.session.open(MessageBox, "\nDie E-Mail Funktion ist nicht aktiviert. Aktivieren Sie die E-Mail Funktion im Setup des Plugins.", MessageBox.TYPE_INFO, timeout=5, close_on_any_key=True)
		if self.current == "menu" and self.sortname:
			self.sort = (self.sort + 1) % len(self.sortname)
			self.curr_item = 0
			callInThread(self.fill_rlist)

	def green_return(self, answer):
		if answer:
			self.send_rezept(answer[0])

	def send_rezept(self, mailTo):
		effort = ["keine", "simpel", "normal", "pfiffig"]
		msgText = f'<p>Linkadresse: <a href="{self.rezept}{self.curr_id}">{self.rezept}{self.curr_id}</a></p>'
		scoretext = f"{self.rez.get('rating', '').get('rating', ''):1.1f} ({self.rez.get('rating', '').get('numVotes', '')} Bewertungen)" if self.rez and self.rez.get("rating", "") else "(ohne Bewertung)"
		preptime = self.rez.get("preparationTime", "") if self.rez else ""
		cooktime = self.rez.get("cookingTime", "") if self.rez else ""
		resttime = self.rez.get("restingTime", "") if self.rez else ""
		totaltime = self.rez.get("totalTime", "") if self.rez else ""
		if preptime != 0:
			scoretext += f"\nArbeitszeit   : {self.get_time_string(preptime)}"
		if cooktime != 0:
			scoretext += f"\nKoch-/Backzeit: {self.get_time_string(cooktime)}"
		if resttime != 0:
			scoretext += f"\nRuhezeit      : {self.get_time_string(resttime)}"
		if totaltime != 0:
			scoretext += f"\nGesamtzeit    : {self.get_time_string(totaltime)}"
		msgText += scoretext
		recipetext = f"\n\nRezept-Identnr.: {self.curr_id}"
		recipetext += f"\nAufwand: {effort[self.rez.get('difficulty', '')] if self.rez else ''}"
		recipetext += f"\nErstellername : {self.format_username(self.rez.get('owner', '').get('username', ''), self.rez.get('owner', '').get('rank', ''), 22) if self.rez else ''}"
		recipetext += f"\nErstelldatum: {self.format_datum(self.rez.get('createdAt', '')) if self.rez else ''}"
		if self.rez and self.rez.get("nutrition", ""):
			kcalori = self.rez.get("nutrition", "").get("kCalories", "")
			kcalori = str(kcalori) if kcalori else "k.A."
			protein = self.rez.get("nutrition", "").get("proteinContent", "")
			protein = f"{protein}g" if protein else "k.A."
			fatcont = self.rez.get("nutrition", "").get("fatContent", "")
			fatcont = f"{fatcont}g" if fatcont else "k.A."
			carbohyd = self.rez.get("nutrition", "").get("carbohydrateContent", "")
			carbohyd = f"{carbohyd}g" if carbohyd else "k.A."
			recipetext += "\n\nkcal  Eiweiß  Fett  Kohlenhydr."
			recipetext += f"\n{kcalori} {protein} {fatcont} {carbohyd}"
		msgText += f"{recipetext}\n\n"
		if self.rez and self.rez.get("subtitle", ""):
			msgText += f"BESCHREIBUNG: {self.rez.get('subtitle', '')}\n\n"
		msgText += "ZUTATEN\n"
		for i in range(len(self.rez.get("ingredientGroups", "")) if self.rez else 0):
			for j in range(len(self.rez.get("ingredientGroups", "")[i].get("ingredients", "")) if self.rez else 0):
				if not (i == 0 and j == 0):
					msgText += "; "
				if self.rez and self.rez.get("ingredientGroups", "")[i].get("ingredients", "")[j].get("amount", "") != 0:
					msgText += f"{str(self.rez.get('ingredientGroups', '')[i].get('ingredients', '')[j].get('amount', '')).replace('.0', '')} "
					msgText += f"{self.rez.get('ingredientGroups', '')[i].get('ingredients', '')[j].get('unit', '')} "
				msgText += self.rez.get("ingredientGroups", "")[i].get("ingredients", "")[j].get("name", "") if self.rez else ""
				msgText += self.rez.get("ingredientGroups", "")[i].get("ingredients", "")[j].get("usageInfo", "") if self.rez else ""
		msgText += f"\n\nZUBEREITUNG\n{self.rez.get('instructions', '')}" if self.rez else ""
		msgText += f"\n{'_' * 30}\nChefkoch.de"
		if fileExists(ckglobals.pic_file):
			Image.open(ckglobals.pic_file).resize((320, 240), Image.Resampling.LANCZOS).save("/tmp/emailpic.jpg")
		mailFrom = config.plugins.chefkoch.mailfrom.value
		mailLogin = config.plugins.chefkoch.login.value
		mailPassword = b64decode(config.plugins.chefkoch.password.value).decode()
		mailServer = config.plugins.chefkoch.server.value
		mailPort = config.plugins.chefkoch.port.value
		msgRoot = MIMEMultipart("related")
		msgRoot["Subject"] = f"Chefkoch.de: {self.titel}"
		msgRoot["From"] = mailFrom
		msgRoot["To"] = mailTo  # bei Bedarf ergänzbar: msgRoot['Cc'] =cc
		msgRoot.preamble = "Multi-part message in MIME format."
		msgAlternative = MIMEMultipart("alternative")
		msgRoot.attach(msgAlternative)
		msgAlternative.attach(MIMEText(msgText, _subtype="plain", _charset="UTF-8"))
		msgHeader = f"'{self.titel}' gesendet vom Plugin 'Chefkoch.de'"
		msgText = msgText.replace("\n", "<br>")
		msgAlternative.attach(MIMEText(f'<b>{msgHeader}</b><br><br><img src="cid:0"><br>{msgText}', "html"))
		with open("/tmp/emailpic.jpg", "rb") as img:
			msgImage = MIMEImage(img.read(), _subtype="jpeg")
		msgImage.add_header("Content-ID", "<0>")
		msgRoot.attach(msgImage)
		if self.send_email(mailServer, mailLogin, mailPassword, msgRoot, config.plugins.chefkoch.starttls.value, mailPort):
			self.ck_log(f"Email sent successfully to {mailTo}.")
			self.session.open(MessageBox, f"E-Mail an {mailTo} erfolgreich gesendet.", MessageBox.TYPE_INFO, timeout=5, close_on_any_key=True)
		else:
			self.ck_log(f"The email to {mailTo} could not be sent.")
			self.session.open(MessageBox, f"E-Mail an {mailTo} konnte nicht versendet werden.", MessageBox.TYPE_INFO, timeout=5, close_on_any_key=True)

	def send_email(self, mailServer, username, password, message, starttls=True, mailPort=None):
		tls_context = create_default_context()
		try:
			if starttls:  # STARTTLS, typically port 587
				with SMTP(mailServer, mailPort or 587, timeout=30) as server:
					server.ehlo()
					server.starttls(context=tls_context)
					server.ehlo()
					server.login(username, password)
					server.send_message(message)
			else:  # implicit SSL/TLS, typically port 465
				with SMTP_SSL(mailServer, mailPort or 465, context=tls_context, timeout=30) as server:
					server.ehlo()
					server.login(username, password)
					server.send_message(message)
			return True
		except SMTPAuthenticationError as error:
			self.ck_log(f"SMTP login failed: {error}")
			self.session.open(MessageBox, f"E-Mail konnte aufgrund eines Serverproblems oder fehlerhafter\nAnmeldedaten (Login oder Passwort) nicht gesendet werden!\nERROR: {error}", MessageBox.TYPE_ERROR, timeout=10, close_on_any_key=True)
		except SMTPConnectError as error:
			self.ck_log(f"Connection to the SMTP server failed: {error}")
			self.session.open(MessageBox, f"Verbindung zum SMTP-Server fehlgeschlagen: {error}", MessageBox.TYPE_ERROR, timeout=10, close_on_any_key=True)
		except SMTPException as error:
			self.ck_log(f"SMTP error: {error}")
			self.session.open(MessageBox, f"SMTP-Fehler: {error}", MessageBox.TYPE_ERROR, timeout=10, close_on_any_key=True)
		except OSError as error:
			self.ck_log(f"Network or TLS error: {error}")
			self.session.open(MessageBox, f"Netzwerk- oder TLS-Fehler: {error}", MessageBox.TYPE_ERROR, timeout=10, close_on_any_key=True)
		return False

	def next_page(self):
		if self.current == "menu":
			self.curr_item = self["menu"].getSelectedIndex()
			offset = self.curr_item % ckglobals.lines_per_page
			if self.curr_item + ckglobals.lines_per_page > self.len - 1 and offset > (self.len - 1) % ckglobals.lines_per_page:
				self.curr_item = self.len - 1
				self["menu"].moveToIndex(self.curr_item)  # springe auf letzten Eintrag der letzten Seite
				self.set_prev_icons(self.curr_item - offset)
			elif self.curr_item + ckglobals.lines_per_page > self.len - 1:
				self.curr_item = offset
				self["menu"].moveToIndex(self.curr_item)  # springe auf gleichen Offset der ersten Seite
				self.set_prev_icons(0)
			else:
				self.curr_item = self.curr_item + ckglobals.lines_per_page
				self["menu"].pageDown()
				self.set_prev_icons(self.curr_item - offset)
			self["label_rezeptnr"].setText(f"Rezept Nr. {self.curr_item + 1}")
			self["pageinfo"].setText(f"Seite {int(self.curr_item // ckglobals.lines_per_page + 1)} von {self.max_page}")
		else:
			self["textpage"].pageDown()

	def prev_page(self):
		if self.current == "menu":
			self.curr_item = self["menu"].getSelectedIndex()
			offset = self.curr_item % ckglobals.lines_per_page
			lasttop = (self.len - 1) // ckglobals.lines_per_page * ckglobals.lines_per_page
			if self.curr_item - ckglobals.lines_per_page < 0 and offset > (self.len - 1) % ckglobals.lines_per_page:
				self.curr_item = self.len - 1
				self["menu"].moveToIndex(self.curr_item)  # springe auf gleichen Offset der vorherigen Seite
				self.set_prev_icons(lasttop)
			elif self.curr_item - ckglobals.lines_per_page < 0:
				self.curr_item = lasttop + offset
				self["menu"].moveToIndex(self.curr_item)  # springe auf letzten Eintrag der letzten Seite
				self.set_prev_icons(lasttop)
			else:
				self.curr_item = self.curr_item - ckglobals.lines_per_page
				self["menu"].pageUp()
				self.set_prev_icons(self.curr_item - offset)
			self["label_rezeptnr"].setText(f"Rezept Nr. {self.curr_item + 1}")
			self["pageinfo"].setText(f"Seite {int(self.curr_item // ckglobals.lines_per_page + 1)} von {self.max_page}")
		else:
			self["textpage"].pageUp()

	def down(self):
		if self.current == "menu":
			self["menu"].down()
			self.curr_item = self["menu"].getSelectedIndex()
			self["label_rezeptnr"].setText(f"Rezept Nr. {self.curr_item + 1}")
			self["pageinfo"].setText(f"Seite {int(self.curr_item // ckglobals.lines_per_page + 1)} von {self.max_page}")
			if self.curr_item == self.len:  # neue Vorschaubilder der ersten Seite anzeigen
				self.set_prev_icons(0)
			if self.curr_item % ckglobals.lines_per_page == 0:  # neue Vorschaubilder der nächsten Seite anzeigen
				self.set_prev_icons(self.curr_item)
		else:
			self["textpage"].pageDown()

	def up(self):
		if self.current == "menu":
			self["menu"].up()
			self.curr_item = self["menu"].getSelectedIndex()
			self["label_rezeptnr"].setText(f"Rezept Nr. {self.curr_item + 1}")
			self["pageinfo"].setText(f"Seite {int(self.curr_item // ckglobals.lines_per_page + 1)} von {self.max_page}")
			if self.curr_item == self.len - 1:  # neue Vorschaubilder der letzte Seite anzeigen
				d = self.len % ckglobals.lines_per_page if self.len % ckglobals.lines_per_page != 0 else ckglobals.lines_per_page
				self.set_prev_icons(self.len - d)
			if self.curr_item % ckglobals.lines_per_page == ckglobals.lines_per_page - 1:  # neue Vorschaubilder der vorherige Seite anzeigen
				self.set_prev_icons(self.curr_item // ckglobals.lines_per_page * ckglobals.lines_per_page)
		else:
			self["textpage"].pageUp()

	def goto_page(self, number):
		if self.current == "postview" and number == 0:
			self["textpage"].lastPage()
		elif self.current == "postview" and number == 1 and self.comment:
			self.show_comments()
		elif self.current == "postview" and number == 1:
			self.show_rezept()
		else:
			self.session.openWithCallback(self.number_entered, CKgetNumber, number, self.max_pics)

	def number_entered(self, number):
		if number and number != 0:
			count = int(number)
			if count > self.max_page:
				count = self.max_page
				self.session.open(MessageBox, f"\nNur {count} Seiten verfügbar. Gehe zu Seite {count}.", MessageBox.TYPE_INFO, timeout=2, close_on_any_key=True)
			self.curr_item = (count - 1) * ckglobals.lines_per_page
			self["menu"].moveToIndex(self.curr_item)
			self.set_prev_icons(self.curr_item)
			self["label_rezeptnr"].setText(f"Rezept Nr. {self.curr_item + 1}")
			self["pageinfo"].setText(f"Seite {int(self.curr_item // ckglobals.lines_per_page + 1)} von {self.max_page}")

	def set_prev_icons(self, toppos):
		for index in range(ckglobals.lines_per_page):
			if len(self.picurllist) > toppos + index:
				callInThread(self.pic_download, self.picurllist[toppos + index], index)
				if self.videolist[toppos + index]:
					self[f"vid{index}"].show()
				else:
					self[f"vid{index}"].hide()
			else:
				self[f"pic{index}"].hide()
				self[f"vid{index}"].hide()

	def yellow(self):
		if self.current == "menu":
			self.curr_item = self["menu"].getSelectedIndex()
			self.session.open(CKfavoriten, False)
		elif self.current == "postview" and self.kom_len > 0 and self.comment:
			self.comment = False
			self.show_rezept()
		elif self.current == "postview" and self.kom_len > 0:
			self.comment = True
			self.show_comments()

	def show_comments(self):  # zeige leere Kommentaransicht
		self["label_yellow"].setText("Beschreibung einblenden")
		self["label_1-0"].setText("Erster/Letzer Kommentar")
		self["label_1-0"].show()
		self["button_1-0"].show()
		if self.pic_count == 1:
			self["label_ok"].setText("Vollbild")
			self["button_ok"].show()
		elif self.pic_count > 1:
			self["label_ok"].setText(f"{self.img_len} Rezeptbilder")
			self["button_ok"].show()
		else:
			self["label_ok"].setText("")
			self["button_ok"].hide()
		self["pageinfo"].hide()
		self["textpage"].setText("")
		callInThread(self.fill_comments)

	def fill_comments(self):  # fülle die Kommentaransicht
		text = ""
		for idx, kom in enumerate(self.kom.get("results", "")):
			text += f"Kommentar {idx + 1}/{self.kom_len} von "
			text += self.format_username(kom.get("owner", "").get("username", ""), kom.get("owner", "").get("rank", ""), 0)
			text += f" {self.format_datum_zeit(kom.get('createdAt', ''))} Uhr\n"
			text += kom.get("text", "")
			if ckglobals.resolution == "FHD":
				repeat = 102 if config.plugins.chefkoch.bigfontsize.value else 109
				text += f"\n{'_' * repeat}\n"
			else:
				repeat = 96 if config.plugins.chefkoch.bigfontsize.value else 105
				text += f"\n{'_' * repeat}\n"
		text += "\nChefkoch.de"
		self["textpage"].setText(text)

	def show_rezept(self):  # zeige leere Rezeptansicht
		self["button_green"].show()
		self["label_green"].setText("Rezept per Email")
		self["label_1-0"].setText("")
		self["button_1-0"].hide()
		self["pageinfo"].setText("")
		if self.kom_len > 0:
			self["label_yellow"].setText(f"{self.kom_len} Kommentare einblenden")
			self["button_yellow"].show()
		else:
			self["label_yellow"].setText("")
			self["button_yellow"].hide()
		self["label_rezeptnr"].setText("")
		if self.pic_count == 1:
			self["label_ok"].setText("Vollbild")
			self["button_ok"].show()
		elif self.pic_count > 1:
			self["label_ok"].setText(f"{self.img_len} Rezeptbilder")
			self["button_ok"].show()
		else:
			self["label_ok"].setText("")
			self["button_ok"].hide()
		self["textpage"].setText("")
		if self.rez and self.rez.get("hasVideo", ""):
			self["postvid"].show()
			self["label_play"].setText("Video abspielen")
			self["label_play"].show()
			self["button_play"].show()
		else:
			self["postvid"].hide()
			self["label_play"].hide()
			self["button_play"].hide()
		callInThread(self.fill_rezept)

	def fill_rezept(self):  # fülle die Rezeptansicht
		text = ""
		if self.rez and self.rez.get("subtitle", ""):
			text += f"BESCHREIBUNG: {self.rez.get('subtitle', '')}\n\n"
		text += "ZUTATEN\n"
		for i in range(len(self.rez.get("ingredientGroups", "")) if self.rez else 0):
			for j in range(len(self.rez.get("ingredientGroups", "")[i].get("ingredients", "")) if self.rez else 0):
				if not (i == 0 and j == 0):
					text += "; "
				if self.rez and self.rez.get("ingredientGroups", "")[i].get("ingredients", "")[j].get("amount", "") != 0:
					text += f"{str(self.rez.get('ingredientGroups', '')[i].get('ingredients', '')[j].get('amount', '')).replace('.0', '')} "
					text += f"{self.rez.get('ingredientGroups', '')[i].get('ingredients', '')[j].get('unit', '')} "
				text += self.rez.get("ingredientGroups", "")[i].get("ingredients", "")[j].get("name", "") if self.rez else ""
				text += self.rez.get("ingredientGroups", "")[i].get("ingredients", "")[j].get("usageInfo", "") if self.rez else ""
		text += f"\n\nZUBEREITUNG\n{self.rez.get('instructions', '')}" if self.rez else ""
		if ckglobals.resolution == "FHD":
			repeat = 102 if config.plugins.chefkoch.bigfontsize.value else 109
		else:
			repeat = 96 if config.plugins.chefkoch.bigfontsize.value else 105
		text += f"\n{'_' * repeat}\nChefkoch.de"
		self["textpage"].setText(str(text))
		self["picture"].show()

	def zap(self):
		servicelist = self.session.instantiateDialog(ChannelSelection)
		self.session.execDialog(servicelist)

	def eject(self, answer):
		self.exit()

	def exit(self):
		global hideflag
		if ckglobals.alpha and not hideflag:
			hideflag = True
			with open(ckglobals.alpha, "w") as f:
				f.write(f"{config.av.osd_ckglobals.ALPHA.value}")
		if self.current == "menu":
			self.close()
		elif self.fav:
			self.close()
		elif self.current == "postview" and self.zufall:
			self.close()
		elif self.current == "postview" and not self.zufall:
			self.current = "menu"
			self.show_rlist()
			callInThread(self.fill_rlist)

	def play_video(self):
		if self.current == "menu":
			self.rez = self.get_rez(self.grp_s[self.curr_item].get("id", ""))
		if self.rez and self.rez.get("recipeVideoId", ""):
			result, resp = self.get_api_data(apiurl=f"videos/{self.rez.get('recipeVideoId', '')}")
			if resp != 200:
				self.session.openWithCallback(self.eject, MessageBox, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
				self.close()
				return
			if videourl := result.get("video_targetvideo_url"):
				sref = eServiceReference(4097, 0, videourl)
				videotitle = result.get("video_title", "")
				description = result.get("video_description", "")
				if len(f"{videotitle} - {description}") < 30:
					sref.setName(f"{videotitle} - {description}")
				else:
					sref.setName(videotitle)
				try:
					self.session.open(MoviePlayer, sref, fromMovieSelection=False)
				except Exception:  # in case image doesn't support 'fromMovieSelection'
					self.session.open(MoviePlayer, sref)


class CKgetNumber(AllScreen):
	skin = """
	<screen name="CKgetNumber" position="center,center" size="175,70" resolution="1280,720" backgroundColor="#00000000" flags="wfNoBorder" title=" ">
		<widget name="number" position="0,0" size="175,70" font="Regular;40" halign="center" valign="center" transparent="1" zPosition="1" />
	</screen>"""

	def __init__(self, session, number, maxPics):
		Screen.__init__(self, session, self.skin)
		self.field = str(number)
		self.max_pics = maxPics
		self["number"] = Label(self.field)
		self["actions"] = NumberActionMap(["SetupActions"], {
			"cancel": self.quit,
			"ok": self.key_ok,
			"1": self.key_number,
			"2": self.key_number,
			"3": self.key_number,
			"4": self.key_number,
			"5": self.key_number,
			"6": self.key_number,
			"7": self.key_number,
			"8": self.key_number,
			"9": self.key_number,
			"0": self.key_number
		}, -1)
		self.t_imer = eTimer()
		self.t_imer.callback.append(self.key_ok)
		self.t_imer.start(2500, True)

	def key_number(self, number):
		self.t_imer.start(2000, True)
		self.field = f"{self.field}{number}"
		self["number"].setText(self.field)
		if len(self.field) >= 3:
			self.key_ok()

	def key_ok(self):
		self.t_imer.stop()
		self.close(int(self["number"].getText()))

	def quit(self):
		self.t_imer.stop()
		self.close(0)


class CKpicshow(AllScreen):
	skin = """
		<screen name="CKpicshow" position="center,center" size="1280,720" resolution="1280,720" title="" flags="wfNoBorder" backgroundColor="background">
			<ePixmap position="0,0" size="1920,1080" pixmap="{picpath}/background.png" zPosition="-10" />
			<widget source="Title" render="Label" position="center,13" size="1000,32" font="Regular; 24" transparent="1" foregroundColor="#336f3d" backgroundColor="white" halign="center" valign="center" zPosition="3" />
			<ePixmap position="0,0" size="1280,60" pixmap="{picpath}/chefkoch.png" alphatest="blend" zPosition="1" />
			<widget name="release" position="43,25" size="40,19" font="Regular; 14" foregroundColor="#697279" backgroundColor="white" halign="left" valign="center" transparent="1" zPosition="2" />
			<widget name="scoretext" position="15,130" size="260,50" font="Regular;20" foregroundColor="white" backgroundColor="background" halign="left" zPosition="1" transparent="1" />
			<widget name="picture" position="270,70" size="720,540" scaleFlags="centerScaled" alphatest="blend" zPosition="1" />
			<widget name="picindex" position="1000,70" size="250,260" foregroundColor="white" backgroundColor="background" font="Regular;22" halign="left" zPosition="1" transparent="1" />
			<widget name="pictext" position="30,615" size="1220,48" font="Regular;22" foregroundColor="white" backgroundColor="background" halign="center" valign="center" zPosition="1" transparent="1" />
			<eLabel name="Line_Bottom" position="0,675" size="1280,1" backgroundColor="#3B8047" zPosition="3" />
			<widget name="label_left-right" position="665,688" size="240,24" font="Regular;18" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="2" />
			<widget name="button_left-right" position="625,685" size="30,30" pixmap="{picpath}/left-right.png" alphatest="blend" zPosition="1" />
			<widget name="label_ok" position="365,689" size="240,24" font="Regular;18" foregroundColor="white" backgroundColor="background" halign="left" transparent="1" zPosition="2" />
			<widget name="button_ok" position="325,685" size="30,30" pixmap="{picpath}/ok.png" alphatest="blend" zPosition="1" />
			<widget name="starsbg" position="15,75" size="228,40" pixmap="{picpath}/starsbar_empty.png" transparent="1"  zPosition="0" alphatest="blend" />
			<widget name="stars" position="15,75" size="228,40" pixmap="{picpath}/starsbar_filled.png"  transparent="1"  />
		</screen>"""

	def __init__(self, session, titel, recipe, images):
		global hideflag
		hideflag = True
		self.skin = self.skin.replace("{picpath}", f"{ckglobals.plugin_path}/pic/{ckglobals.resolution}")
		Screen.__init__(self, session, self.skin)
		self.session = session
		self.rez = recipe
		self.img = images
		self.titel = titel
		self.curr_id = str(recipe["id"])
		self.setTitle(titel)
		self.pixlist = []
		self.max_pics = 0
		self.count = 0
		self["stars"] = ProgressBar()
		self["starsbg"] = Pixmap()
		self["stars"].hide()
		self["starsbg"].hide()
		self["scoretext"] = Label("")
		self["scoretext"].hide()
		self["picture"] = Pixmap()
		self["picture"].show()
		self["picindex"] = Label("")
		self["pictext"] = Label("")
		self["label_ok"] = Label()
		self["button_ok"] = Pixmap()
		self["label_left-right"] = Label("")
		self["button_left-right"] = Pixmap()
		self["release"] = Label(ckglobals.release)
		self["NumberActions"] = NumberActionMap(["NumberActions", "OkCancelActions", "DirectionActions", "ColorActions", "HelpActions"], {
			"ok": self.ok,
			"cancel": self.exit,
			"right": self.picup,
			"left": self.picdown,
			"up": self.picup,
			"down": self.picdown,
			"blue": self.hide_screen,
			"0": self.goto_pic,
			"1": self.goto_pic,
			"2": self.goto_pic,
			"3": self.goto_pic,
			"4": self.goto_pic,
			"5": self.goto_pic,
			"6": self.goto_pic,
			"7": self.goto_pic,
			"8": self.goto_pic,
			"9": self.goto_pic,
		}, -1)
		self.onLayoutFinish.append(self.on_layout_finished)

	def on_layout_finished(self):
		self["label_ok"].setText("Vollbild")
		self["button_ok"].show()
		self["label_left-right"].setText("Zurück / Vorwärts")
		self["label_left-right"].show()
		self["button_left-right"].show()
		self.count = 0
		self.setTitle(str(self.titel))
		if self.rez.get("subtitle", ""):
			self["pictext"].setText(f"BESCHREIBUNG: {self.rez.get('subtitle', '')}")
		if self.rez.get("rating", ""):
			score = self.rez.get("rating", "").get("rating", "") * 20
			scoretext = f"{self.rez.get('rating', '').get('rating', '')} ({self.rez.get('rating', '').get('numVotes', '')} Bewertungen)"
		else:
			score = 0.0
			scoretext = "(ohne Bewertung)"
		self["starsbg"].show()
		self["stars"].show()
		self["stars"].setValue(score)
		self["scoretext"].setText(scoretext)
		self["scoretext"].show()
		if self.img.get("count", "") > 0:
			for index in range(len(self.img.get("results", ""))):
				self.pixlist.append(self.img.get("results", "")[index].get("id", ""))
			picurl = f"{ckglobals.pic_url_base}{self.curr_id}/bilder/{self.rez.get('previewImageId', '')}/crop-960x720/{self.titel}.jpg"
			callInThread(self.pic_download, picurl)
			self.max_pics = len(self.pixlist) - 1
			username = self.format_username(self.img.get("results", "")[self.count].get("owner", "").get("username", ""), self.img.get("results", "")[self.count].get("owner", "").get("rank", ""), 22)
			self["picindex"].setText(f"Bild {self.count + 1} von {self.max_pics + 1}\nvon {username}")
		else:
			self.session.open(MessageBox, "\nKein Foto vorhanden", MessageBox.TYPE_INFO, timeout=2, close_on_any_key=True)

	def format_username(self, username, rank, trim=100):
		return "Unbekannt" if "unknown" in username else f"{username} ({rank})"

	def ok(self):
		self.session.openWithCallback(self.show_pic, CKfullscreen)

	def picup(self):
		self.count += 1 if self.count < self.max_pics else - self.count
		picurl = f"{ckglobals.pic_url_base}{self.curr_id}/bilder/{self.img.get('results', '')[self.count].get('id', '')}/crop-960x720/{self.titel}.jpg" if self.rez.get("hasImage", "") else ckglobals.no_pic_url
		callInThread(self.pic_download, picurl)
		username = self.format_username(self.img.get("results", "")[self.count].get("owner", "").get("username", ""), self.img.get("results", "")[self.count].get("owner", "").get("rank", ""), 22)
		self["picindex"].setText(f"Bild {self.count + 1} von {self.max_pics + 1}\nvon {username}")

	def picdown(self):
		self.count -= 1 if self.count > 0 else - self.max_pics
		picurl = f"{ckglobals.pic_url_base}{self.curr_id}/bilder/{self.img.get('results', '')[self.count].get('id', '')}/crop-960x720/{self.titel}.jpg" if self.rez.get("hasImage", "") else ckglobals.no_pic_url
		callInThread(self.pic_download, picurl)
		username = self.format_username(self.img.get("results", "")[self.count].get("owner", "").get("username", ""), self.img.get("results", "")[self.count].get("owner", "").get("rank", ""), 22)
		self["picindex"].setText(f"Bild {self.count + 1} von {self.max_pics + 1}\nvon {username}")

	def goto_pic(self, number):
		self.session.openWithCallback(self.number_entered, CKgetNumber, number, self.max_pics)

	def number_entered(self, number):
		if number > self.max_pics + 1:
			number = self.max_pics + 1
		self.count = number - 1
		picurl = f"{ckglobals.pic_url_base}{self.curr_id}/bilder/{self.img.get('results', '')[self.count].get('id', '')}/crop-960x720/{self.titel}.jpg" if self.rez.get("hasImage", "") else ckglobals.no_pic_url
		self.pixlist[self.count]
		callInThread(self.pic_download, picurl)
		username = self.format_username(self.img.get("results", "")[self.count].get("owner", "").get("username", ""), self.img.get("results", "")[self.count].get("owner", "").get("rank", ""), 22)
		self["picindex"].setText(f"Bild {self.count + 1} von {self.max_pics + 1}\nvon {username}")

	def exit(self):
		if ckglobals.alpha and not hideflag:
			with open(ckglobals.alpha, "w") as f:
				f.write(f"{config.av.osd_ckglobals.ALPHA.value}")
		self.close()


class CKfullscreen(AllScreen):
	skin = """
		<screen name="CKfullscreen" position="center,center" size="1280,720" resolution="1280,720" flags="wfNoBorder" title="" >
			<ePixmap position="0,0" size="1280,720" pixmap="{picpath}/background.png" alphatest="blend" zPosition="-10" />
			<eLabel position="center,center" size="960,720" backgroundColor="#000000" zPosition="1" />
			<widget name="picture" position="center,center" size="960,720" scaleFlags="centerScaled" alphatest="blend" zPosition="2" />
		</screen>"""

	def __init__(self, session):
		global hideflag
		hideflag = True
		self.skin = self.skin.replace("{picpath}", f"{ckglobals.plugin_path}/pic/{ckglobals.resolution}")
		Screen.__init__(self, session, self.skin)
		self.session = session
		self.hideflag = True
		self["picture"] = Pixmap()
		self["picture"].show()
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"],
			{
			"ok": self.exit,
			"cancel": self.exit,
			"blue": self.hide_screen
			}, -1)
		self.onLayoutFinish.append(self.on_layout_finished)

	def on_layout_finished(self):
		self.show_pic()

	def exit(self):
		if ckglobals.alpha and not hideflag:
			with open(ckglobals.alpha, "w") as f:
				f.write(f"{config.av.osd_ckglobals.ALPHA.value}")
		self.close()


class CKfavoriten(AllScreen):
	skin = """
		<screen name="CKfavoriten" position="345,10" size="590,700" resolution="1280,720" title="" flags="wfNoBorder" backgroundColor="background">
			<ePixmap position="0,0" size="1920,1080" pixmap="{picpath}/background.png" zPosition="-10" />
			<widget source="Title" render="Label" position="40,14" size="510,32" font="Regular; 24" transparent="1" foregroundColor="#336f3d" backgroundColor="white" halign="center" valign="center" zPosition="3" />
			<ePixmap position="0,0" size="590,60" pixmap="{picpath}/chefkoch.png" alphatest="blend" zPosition="1" />
			<widget name="release" position="43,25" size="40,19" font="Regular; 14" foregroundColor="#697279" backgroundColor="white" halign="left" valign="center" transparent="1" zPosition="2" />
			<widget name="label_red" position="40,668" size="120,24" font="Regular;18" halign="left" transparent="1" zPosition="2" />
			<eLabel name="button_red" position="15,665" size="8,30" backgroundColor="red" zPosition="2" />
			<widget name="favmenu" position="11,73" size="570,580" foregroundColor="white" backgroundColor="background" backgroundColorSelected="#20336f3d" font="Regular;22" itemHeight="34" selectionPixmap="{picpath}/BG_Pixmap.png" scrollbarMode="showOnDemand" halign="left" zPosition="1" transparent="1"/>
			<eLabel name="Line_Left" position="9,72" size="1,582" backgroundColor="#3B8047" zPosition="3" />
			<eLabel name="Line_Right" position="581,72" size="1,582" backgroundColor="#3B8047" zPosition="3" />
			<eLabel name="Line_Top" position="9,72" size="572,1" backgroundColor="#3B8047" zPosition="3" />
			<eLabel name="Line_Bottom" position="9,654" size="572,1" backgroundColor="#3B8047" zPosition="3" />
		</screen>"""

	def __init__(self, session, favmode=True):
		global hideflag
		hideflag = True
		self.skin = self.skin.replace("{picpath}", f"{ckglobals.plugin_path}/pic/{ckglobals.resolution}")
		Screen.__init__(self, session, self.skin)
		self["release"] = Label(ckglobals.release)
		self.favmode = favmode
		self.session = session
		self.favlist = []
		self.fav_id = []
		self.faventries = []
		self["favmenu"] = ItemList([])
		self["label_red"] = Label("Entferne Favorit") if self.favmode else Label("Entferne Suchbegriff")
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "NumberActions"], {
			"ok": self.ok,
			"cancel": self.exit,
			"down": self.down,
			"up": self.up,
			"red": self.red,
			"0": self.move2end,
			"1": self.move2first
		}, -1)
		self.make_fav()

	def make_fav(self):
		if self.favmode:
			self.setTitle("Chefkoch - Favoriten")
			self.favoriten = ckglobals.favorites
		else:
			self.setTitle("Chefkoch - letzte Suchbegriffe")
			self.favoriten = ckglobals.searches
			titel = ">>> Neue Suche <<<"
			res = [""]
			res.append(MultiContentEntryText(pos=(4, 0), size=(int(570 * ckglobals.scale), int(34 * ckglobals.scale)), font=-2, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=titel))
			self.faventries.append(res)
			self.favlist.append(titel)
			self.fav_id.append("")
		if fileExists(self.favoriten):
			with open(self.favoriten) as f:
				for line in f:
					if ":::" in line:
						favline = line.split(":::")
						titel = str(favline[0])
						res = [""]
						res.append(MultiContentEntryText(pos=(4, 0), size=(int(570 * ckglobals.scale), int(34 * ckglobals.scale)), font=-2, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=titel))
						self.faventries.append(res)
						self.favlist.append(titel)
						self.fav_id.append(favline[1].replace("\n", ""))
		self["favmenu"].l.setList(self.faventries)
		self["favmenu"].l.setItemHeight(int(34 * ckglobals.scale))

	def ok(self):
		self.curr_item = self.get_index(self["favmenu"])
		if len(self.favlist) > 0:
			titel = self.favlist[self.curr_item]
			if self.favmode:
				self.session.open(CKview, self.fav_id[self.curr_item], f"'{titel}'", 1, True, False)
			elif titel == ">>> Neue Suche <<<":
				titel = ""
				self.session.openWithCallback(self.search_return, VirtualKeyBoard, title="Chefkoch - Suche Rezepte:", text=titel)
			else:
				self.session.open(CKview, titel, f"mit '{titel}' gefundene Rezepte", 0, False, False)

	def search_return(self, search):
		if search and search != "":
			found = False
			if fileExists(self.favoriten):
				with open(self.favoriten) as f:
					for line in f:
						if search in line and line != "\n":
							found = True
							break
			if not found:
				with open(self.favoriten, "a") as f:
					f.write(f"{search}:::{search}")
					f.write(linesep)
			self.session.openWithCallback(self.exit, CKview, search, f"mit '{search}' gefundene Rezepte", 0, False, False)

	def red(self):
		if len(self.favlist) > 0:
			try:
				self.curr_item = self.get_index(self["favmenu"])
				name = self.favlist[self.curr_item]
			except IndexError:
				name = ""
			if name not in (">>> Neue Suche <<<", "") and self.favmode:
				text = f"\nRezept '{name}' aus den Favoriten entfernen?"
				self.session.openWithCallback(self.red_return, MessageBox, text, MessageBox.TYPE_YESNO, timeout=10, default=False)
			elif name not in (">>> Neue Suche <<<", ""):
				text = f"\nsuche '{name}' aus den letzten Suchbegriffen entfernen?"
				self.session.openWithCallback(self.red_return, MessageBox, text, MessageBox.TYPE_YESNO, timeout=10, default=False)

	def red_return(self, answer):
		if answer is True:
			self.curr_item = self.get_index(self["favmenu"])
			try:
				favorite = self.fav_id[self.curr_item]
			except IndexError:
				favorite = "NONE"
			if fileExists(self.favoriten):
				data = ""
				with open(self.favoriten) as f:
					for line in f:
						if favorite not in line and line != "\n":
							data = data + line
				newfavs = f"{self.favoriten}.new"
				with open(newfavs, "w") as fnew:
					fnew.write(data)
				rename(newfavs, self.favoriten)
			self.favlist = []
			self.fav_id = []
			self.faventries = []
			self.make_fav()

	def move2first(self):
		self.curr_item = self.get_index(self["favmenu"])
		fav = f"{self.favlist[self.curr_item]}:::{self.fav_id[self.curr_item]}"
		newfavs = f"{self.favoriten}.new"
		with open(newfavs, "w") as fnew:
			fnew.write(fav)
		data = ""
		with open(self.favoriten) as f:
			for line in f:
				if fav not in line and line != "\n":
					data = data + line
		with open(newfavs, "a") as fnew:
			fnew.write(data)
		rename(newfavs, self.favoriten)
		self.favlist = []
		self.fav_id = []
		self.faventries = []
		self.make_fav()

	def move2end(self):
		self.curr_item = self.get_index(self["favmenu"])
		fav = f"{self.favlist[self.curr_item]}:::{self.fav_id[self.curr_item]}"
		data = ""
		with open(self.favoriten) as f:
			for line in f:
				if fav not in line and line != "\n":
					data = data + line
		newfavs = f"{self.favoriten}.new"
		with open(newfavs, "w") as fnew:
			fnew.write(data)
		with open(newfavs, "a") as fnew:
			fnew.write(fav)
		rename(newfavs, self.favoriten)
		self.favlist = []
		self.fav_id = []
		self.faventries = []
		self.make_fav()

	def get_index(self, list):
		return list.getSelectedIndex()

	def down(self):
		self["favmenu"].down()

	def up(self):
		self["favmenu"].up()

	def exit(self):
		if ckglobals.alpha and not hideflag:
			with open(ckglobals.alpha, "w") as f:
				f.write(f"{config.av.osd_ckglobals.ALPHA.value}")
		self.close()


class ItemList(MenuList):
	def __init__(self, items, enableWrapAround=True):
		MenuList.__init__(self, items, enableWrapAround, eListboxPythonMultiContent)
		fontoffset = 2 if config.plugins.chefkoch.bigfontsize.value else 0
		self.l.setFont(-2, gFont("Regular", int(24 * ckglobals.scale)))
		self.l.setFont(-1, gFont("Regular", int((22 + fontoffset) * ckglobals.scale)))
		self.l.setFont(0, gFont("Regular", int((20 + fontoffset) * ckglobals.scale)))
		self.l.setFont(1, gFont("Regular", int((18 + fontoffset) * ckglobals.scale)))
		self.l.setFont(2, gFont("Regular", int((16 + fontoffset) * ckglobals.scale)))


class CKmain(AllScreen):
	skin = """
		<screen name="CKmain" position="345,10" size="590,700" resolution="1280,720" title="kontaktiere den Server..." flags="wfNoBorder" backgroundColor="background">
			<ePixmap position="0,0" size="1920,1080" pixmap="{picpath}/background.png" zPosition="-10" transparent="1"/>
			<widget source="Title" render="Label" position="60,14" size="490,32" font="Regular; 24" transparent="1" foregroundColor="#336f3d" backgroundColor="white" halign="center" valign="center" zPosition="3" />
			<ePixmap position="0,0" size="590,60" pixmap="{picpath}/chefkoch.png"  zPosition="1" />
			<widget name="release" position="43,25" size="40,19" font="Regular; 14" foregroundColor="#697279" backgroundColor="white" halign="left" valign="center" transparent="1" zPosition="2" />
			<widget name="totalrecipes" position="460,43" size="120,16" font="Regular; 14" foregroundColor="#697279" backgroundColor="white" halign="right" transparent="1" zPosition="2" />
			<widget name="mainmenu" position="10,73" size="570,580" font="Regular;22" itemHeight="34" selectionPixmap="{picpath}/BG_Pixmap.png" scrollbarMode="showNever" foregroundColor="white" backgroundColor="background" backgroundColorSelected="#20336f3d" zPosition="2" transparent="1"/>
			<widget name="secondmenu" position="10,73" size="570,580" font="Regular;22" itemHeight="34" selectionPixmap="{picpath}/BG_Pixmap.png" scrollbarMode="showNever" foregroundColor="white" backgroundColor="background" backgroundColorSelected="#20336f3d" zPosition="2" transparent="1"/>
			<widget name="thirdmenu" position="10,73" size="570,580" font="Regular;22" itemHeight="34" selectionPixmap="{picpath}/BG_Pixmap.png" scrollbarMode="showOnDemand" scrollbarBorderWidth="2" scrollbarWidth="10" scrollbarForegroundColor="#b5d7bb" scrollbarBorderColor="#336F3D" foregroundColor="white" backgroundColor="background" backgroundColorSelected="#20336f3d" zPosition="2" transparent="1"/>
			<eLabel position="12,632" size="566,20" font="Regular; 14" text="***  Authors: Kashmir(†), Mr.Servo, jbleyel - skinned by stein17  ***" foregroundColor="grey" backgroundColor="background" halign="center" valign="center" transparent="1" zPosition="4" />
			<widget name="label_red" position="30,668" size="90,24" font="Regular;18" halign="left" transparent="1" zPosition="2" />
			<widget name="label_green" position="140,668" size="90,24" font="Regular;18" halign="left" transparent="1" zPosition="2" />
			<widget name="label_yellow" position="250,668" size="90,24" font="Regular;18" halign="left" transparent="1" zPosition="2" />
			<widget name="label_blue" position="360,668" size="140,24" font="Regular;18" halign="left" transparent="1" zPosition="2" />
			<eLabel name="Rahmen_grün" position="515,668" size="60,24" backgroundColor="#3B8047" zPosition="1" />
			<eLabel name="Füllung" position="517,670" size="56,20" backgroundColor="#c1d2c7" zPosition="2" />
			<eLabel text="Menü" position="517,670" size="56,20" zPosition="5" font="Regular; 14" halign="center" valign="center" foregroundColor="black" backgroundColor="grey" transparent="1" />
			<eLabel name="button_red" position="15,665" size="8,30" backgroundColor="red" zPosition="2" />
			<eLabel name="button_green" position="125,665" size="8,30" backgroundColor="green" zPosition="2" />
			<eLabel name="button_yellow" position="235,665" size="8,30" backgroundColor="yellow" zPosition="2" />
			<eLabel name="button_blue" position="345,665" size="8,30" backgroundColor="blue" zPosition="2" />
			<eLabel name="Line_Left" position="9,72" size="1,582" backgroundColor="#3B8047" zPosition="3" />
			<eLabel name="Line_Right" position="581,72" size="1,582" backgroundColor="#3B8047" zPosition="3" />
			<eLabel name="Line_Top" position="9,72" size="572,1" backgroundColor="#3B8047" zPosition="3" />
			<eLabel name="Line_Bottom" position="9,654" size="572,1" backgroundColor="#3B8047" zPosition="3" />
		</screen>"""

	def __init__(self, session):
		global hideflag
		self.session = session
		hideflag = True
		if not ckglobals.alpha:
			self.ck_log("ckglobals.ALPHAchannel not found! Hide/Show-Function (=blue button) disabled")
		self.skin = self.skin.replace("{picpath}", f"{ckglobals.plugin_path}/pic/{ckglobals.resolution}/")
		Screen.__init__(self, session, self.skin)
		self.apidata = None
		self.main_id = None
		self.rezeptfile = "/tmp/Rezept.html"
		self.actmenu = "mainmenu"
		self["mainmenu"] = ItemList([])
		self["secondmenu"] = ItemList([])
		self["thirdmenu"] = ItemList([])
		self["label_red"] = Label("Favorit")
		self["label_green"] = Label("Zufall")
		self["label_yellow"] = Label("Suche")
		self["label_blue"] = Label("Ein-/Ausblenden")
		self["release"] = Label(ckglobals.release)
		self["totalrecipes"] = Label("")
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "ChannelSelectBaseActions", "InfoActions", "MenuActions"], {
			"ok": self.ok,
			"cancel": self.exit,
			"right": self.right_down,
			"left": self.left_up,
			"down": self.down,
			"up": self.up,
			"nextBouquet": self.zap,
			"prevBouquet": self.zap,
			"red": self.fav,
			"yellow": self.yellow,
			"green": self.zufall,
			"blue": self.hide_screen,
			"menu": self.config
		}, -1)
		self.movie_stop = config.usage.on_movie_stop.value
		self.movie_eof = config.usage.on_movie_eof.value
		config.usage.on_movie_stop.value = "quit"
		config.usage.on_movie_eof.value = "quit"
		self.prepare_paths()
		self.onLayoutFinish.append(self.on_layout_finished)

	def on_layout_finished(self):
		callInThread(self.make_main_menu)

	def ok(self):
		self.curr_item = self.get_index(self[self.actmenu])
		if self.actmenu == "mainmenu" and self.main_id:
			mainId = self.main_id[self.curr_item]
			if mainId == "998":  # Id für CK-Video Hauptmenü (= Secondmenu)
				self.ck_video = True
				self.curr_kat = self.get_vkat()
				callInThread(self.make_second_menu, mainId)
			elif mainId == "996":  # Id für CK-Magazin Hauptmenü (= Secondmenu)
				self.ck_video = False
				self.curr_kat = self.get_mkat()
				callInThread(self.make_second_menu, mainId)
			else:
				self.ck_video = False
				self.curr_kat = self.get_nkat()
				if list(filter(lambda index: index["parentId"] == mainId, self.curr_kat)):
					callInThread(self.make_second_menu, mainId)
				else:
					sort = 4 if mainId == "999" else 1  # Datumsortierung für "Das perfekte Dinner"
					query = f"{self.mainmenuquery[self.curr_item]}&orderBy=6"  # 6= sort by 'createdAt'
					self.session.openWithCallback(self.select_main_menu, CKview, query, f"'{self.mainmenutitle[self.curr_item]}'", sort, False, False)

		elif self.actmenu == "secondmenu":
			secondId = self.second_id[self.curr_item]
			if self.curr_kat and list(filter(lambda index: index["parentId"] == secondId, self.curr_kat)):
				callInThread(self.make_third_menu, secondId)
			else:
				sort = 3 if self.ck_video else 1  # Videosortierung für "Chefkoch Video"
				query = f"{self.secondmenuquery[self.curr_item]}&orderBy=3"  # 3= sort by 'rating'
				self.session.openWithCallback(self.select_second_menu, CKview, query, f"'{self.secondmenutitle[self.curr_item]}'", sort, False, False)

		elif self.actmenu == "thirdmenu":
			sort = 3 if self.ck_video else 1  # Videosortierung für "Chefkoch Video"
			query = f"{self.thirdmenuquery[self.curr_item]}&orderBy=3"  # 3= sort by 'rating'
			self.session.openWithCallback(self.select_third_menu, CKview, query, f"'{self.thirdmenutitle[self.curr_item]}'", sort, False, False)

	def make_main_menu(self):
		result, resp = self.get_api_data(apiurl="recipes", params={"limit": 1})
		if resp != 200:
			self.session.openWithCallback(self.eject, MessageBox, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
			self.close()
			return
		self.setTitle("Hauptmenü")
		self["totalrecipes"].setText(f"{result.get('count', '')} Rezepte")
		self.nkat = []  # Normalkategorien
		self.vkat = []  # Videokategorien
		self.mkat = []  # Magazinkategorien
		self.mainmenulist = []
		self.mainmenuquery = []
		self.mainmenutitle = []
		self.main_id = []
		self.curr_kat = self.get_nkat()
		for index in range(len(self.curr_kat)):
			res = [""]
			if self.curr_kat[index]["level"] == 1:
				res.append(MultiContentEntryText(pos=(0, 1), size=(int(570 * ckglobals.scale), int(30 * ckglobals.scale)), font=-2, flags=RT_HALIGN_CENTER, text=str(self.curr_kat[index]["descriptionText"])))
				self.mainmenulist.append(res)
				self.mainmenuquery.append(self.curr_kat[index]["descriptionText"])
				self.mainmenutitle.append(self.curr_kat[index]["descriptionText"])
				self.main_id.append(self.curr_kat[index]["id"])
		self["mainmenu"].l.setList(self.mainmenulist)
		self["mainmenu"].l.setItemHeight(int(34 * ckglobals.scale))
		self.select_main_menu()

	def make_second_menu(self, parentId):
		self.secondmenulist = []
		self.secondmenuquery = []
		self.secondmenutitle = []
		self.second_id = []
		self.parent_id = parentId
		if self.curr_kat:
			for index in range(len(self.curr_kat)):
				res = [""]
				if self.curr_kat[index]["level"] == 2 and self.curr_kat[index]["parentId"] == parentId:
					res.append(MultiContentEntryText(pos=(0, 1), size=(int(570 * ckglobals.scale), int(30 * ckglobals.scale)), font=-2, flags=RT_HALIGN_CENTER, text=str(self.curr_kat[index]["descriptionText"])))
					self.secondmenulist.append(res)
					self.secondmenuquery.append(self.curr_kat[index]["descriptionText"])
					self.secondmenutitle.append(self.curr_kat[index]["descriptionText"])
					self.second_id.append(self.curr_kat[index]["id"])
			self["secondmenu"].l.setList(self.secondmenulist)
			self["secondmenu"].l.setItemHeight(int(34 * ckglobals.scale))
			self["secondmenu"].moveToIndex(0)
			for currkat in self.curr_kat:
				if currkat["id"] == parentId:
					self.setTitle(currkat["title"])
					break
			self.select_second_menu()

	def make_third_menu(self, parentId):
		self.thirdmenulist = []
		self.thirdmenuquery = []
		self.thirdmenutitle = []
		if self.curr_kat:
			for currkat in self.curr_kat:
				res = [""]
				if currkat["level"] == 3 and currkat["parentId"] == parentId:
					res.append(MultiContentEntryText(pos=(0, 1), size=(int(570 * ckglobals.scale), int(30 * ckglobals.scale)), font=-2, flags=RT_HALIGN_CENTER, text=currkat["descriptionText"]))
					self.thirdmenulist.append(res)
					self.thirdmenuquery.append(currkat["descriptionText"])
					self.thirdmenutitle.append(currkat["descriptionText"])
			self["thirdmenu"].l.setList(self.thirdmenulist)
			self["thirdmenu"].l.setItemHeight(int(34 * ckglobals.scale))
			self["thirdmenu"].moveToIndex(0)
			for currkat in self.curr_kat:
				if currkat["id"] == parentId:
					self.setTitle(currkat["title"])
					break
			self.select_third_menu()

	def make_vkat_db(self):  # hole alle verfügbaren Videokategorien
		result, resp = self.get_api_data(apiurl="videos", params={"offset": 0, "limit": 10000})
		if resp != 200:
			self.session.openWithCallback(self.eject, MessageBox, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
			self.close()
			return
		seen_formats = []
		with open(ckglobals.vkat_db, "a") as f:
			for index in range(len(result)):
				data = result[index].get("video_format", "")
				format_id = "".join(x for x in data if x.isdigit())
				if data != "unknown" and format_id not in seen_formats:
					seen_formats.append(format_id)
					f.write(f"{data}|{data}\n")

	def get_nkat(self):  # erzeuge die normale Kategorie
		if not self.nkat:
			result, resp = self.get_api_data(apiurl="recipes/categories")
			if resp != 200:
				self.session.openWithCallback(self.eject, MessageBox, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
				self.close()
				return []
			self.nkat = list(result)
			self.nkat.extend([
				{"id": "996", "title": "Chefkoch Magazin", "parentId": None, "level": 1, "descriptionText": "Chefkoch Magazin", "linkName": f"{ckglobals.base_url}/magazin/"},
				{"id": "998", "title": "Chefkoch Videos", "parentId": None, "level": 1, "descriptionText": "Chefkoch Videos", "linkName": f"{ckglobals.base_url}/video.html"},
				{"id": "999", "title": "Perfekte Dinner", "parentId": None, "level": 1, "descriptionText": "Das perfekte Dinner Rezepte", "linkName": f"{ckglobals.base_url}/das-perfekte-dinner.html"},
			])
		return self.nkat

	def get_vkat(self):  # erzeuge die Videokategorie
		if not self.vkat:
			self.vkat.extend(item for item in self.nkat if item.get("level") == 1)
			if not fileExists(ckglobals.vkat_db):
				self.make_vkat_db()  # wird nur bei fehlender VKATdb erzeugt (= Notfall)
			index = 1000  # erzeuge eigene Video-IDs über 1000
			with open(ckglobals.vkat_db) as f:
				for data in f:
					vdict = {}
					vdict["id"] = str(index)
					vdict["title"] = data.split("|")[1].replace("\n", "")
					if data.split("|")[0].startswith("drupal"):
						vdict["parentId"] = "998"  # Id für CK-Video Hauptmenü (= Secondmenu)
						vdict["level"] = 2
					else:
						vdict["parentId"] = "997"  # Id für CK-Video Untermenü (= Thirdmenu)
						vdict["level"] = 3
					vdict["descriptionText"] = data.split("|")[1].replace("\n", "")
					vdict["linkName"] = data.split("|")[0]
					self.vkat.append(vdict)
					index += 1
			self.vkat.append({"id": "997", "title": "weitere Videos", "parentId": "998", "level": 2, "descriptionText": ">>> weitere Chefkoch Videos <<<", "linkName": ""})
		return self.vkat

	def get_mkat(self):  # erzeuge die Magazinkategorie
		if not self.mkat:
			result, resp = self.get_api_data(apiurl="magazine/categories")
			if resp != 200:
				self.session.openWithCallback(self.eject, f"\nFehlermeldung vom Chefkoch.de Server: {resp}", MessageBox.TYPE_INFO, timeout=30, close_on_any_key=True)
				self.close()
				return
			offset = 2000  # erzeuge eigene Magazin-IDs über 2000
			root_entries = []
			for index in range(len(result)):
				mdict = {}
				if result[index].get("parent", "") == "34" and result[index].get("published", ""):  # Id 34 ist die Root von CK-Magazin
					mdict["id"] = str(int(result[index].get("id", "")) + offset)
					mdict["title"] = result[index].get("name", "")
					mdict["parentId"] = "996"  # Id für CK-Magazin Hauptmenü (= Secondmenu)
					mdict["level"] = 2
					mdict["descriptionText"] = result[index].get("name", "")
					mdict["linkName"] = result[index].get("url", "")
					root_entries.append(mdict)
			self.mkat.extend(root_entries)
			child_entries = []
			for index in range(len(result)):
				for j in range(len(self.mkat)):
					mdict = {}
					parentId = result[index].get("parent", "")
					if parentId and int(parentId) + offset == int(self.mkat[j]["id"]):
						mdict["id"] = str(int(result[index].get("id", "")) + offset)
						mdict["title"] = result[index].get("name", "")
						mdict["parentId"] = str(int(parentId) + offset)
						mdict["level"] = 3
						mdict["descriptionText"] = result[index].get("name", "")
						mdict["linkName"] = result[index].get("url", "")
						child_entries.append(mdict)
						break
			self.mkat.extend(child_entries)
			self.mkat.reverse()
			self.mkat.append({"id": "996", "title": "Chefkoch Magazin", "parentId": None, "level": 1, "descriptionText": "Chefkoch Magazin", "linkName": f"{ckglobals.base_url}/magazin/"})
		return self.mkat

	def select_main_menu(self):
		self.actmenu = "mainmenu"
		self["mainmenu"].show()
		self["secondmenu"].hide()
		self["thirdmenu"].hide()
		self["mainmenu"].selectionEnabled(1)
		self["secondmenu"].selectionEnabled(0)
		self["thirdmenu"].selectionEnabled(0)

	def select_second_menu(self):
		if len(self.secondmenulist) > 0:
			self.actmenu = "secondmenu"
			self["mainmenu"].hide()
			self["secondmenu"].show()
			self["thirdmenu"].hide()
			self["mainmenu"].selectionEnabled(0)
			self["secondmenu"].selectionEnabled(1)
			self["thirdmenu"].selectionEnabled(0)

	def select_third_menu(self):
		if len(self.thirdmenulist) > 0:
			self.actmenu = "thirdmenu"
			self["mainmenu"].hide()
			self["secondmenu"].hide()
			self["thirdmenu"].show()
			self["mainmenu"].selectionEnabled(0)
			self["secondmenu"].selectionEnabled(0)
			self["thirdmenu"].selectionEnabled(1)

	def up(self):
		self[self.actmenu].up()

	def down(self):
		self[self.actmenu].down()

	def left_up(self):
		self[self.actmenu].pageUp()

	def right_down(self):
		self[self.actmenu].pageDown()

	def get_index(self, list):
		return list.getSelectedIndex()

	def yellow(self):
		self.session.open(CKfavoriten, False)

	def fav(self):
		self.session.open(CKfavoriten)

	def zufall(self):
		self.session.openWithCallback(self.select_main_menu, CKview, "recipe-of-today", ' "Zufallsrezept"', 1, False, True)

	def zap(self):
		servicelist = self.session.instantiateDialog(ChannelSelection)
		self.session.execDialog(servicelist)

	def config(self):
		config.usage.on_movie_stop.value = self.movie_stop
		config.usage.on_movie_eof.value = self.movie_eof
		self.session.open(CKconfig)

	def eject(self, dummy):
		self.exit()

	def exit(self):
		global hideflag
		if ckglobals.alpha and not hideflag:
			hideflag = True
			with open(ckglobals.alpha, "w") as f:
				f.write(f"{config.av.osd_ckglobals.ALPHA.value}")
		if self.actmenu == "mainmenu":
			config.usage.on_movie_stop.value = self.movie_stop
			config.usage.on_movie_eof.value = self.movie_eof
			for index in range(ckglobals.lines_per_page):
				pic = f"/tmp/chefkoch{index}.jpg"
				if fileExists(pic):
					remove(pic)
			if fileExists(ckglobals.pic_file):
				remove(ckglobals.pic_file)
			if fileExists(self.rezeptfile):
				remove(self.rezeptfile)
			self.close()
		elif self.actmenu == "secondmenu":
			self.curr_kat = self.get_nkat()
			self.setTitle("Hauptmenü")
			self.select_main_menu()
		elif self.actmenu == "thirdmenu" and self.curr_kat:
			for currkat in self.curr_kat:
				if currkat["id"] == self.parent_id:
					self.setTitle(currkat["title"])
					break
			self.select_second_menu()
		elif self.actmenu == "thirdmenu":
			self.select_second_menu()


class CKconfig(AllScreen, Setup):
	def __init__(self, session):
		Setup.__init__(self, session, "CKConfig", plugin="Extensions/Chefkoch", PluginLanguageDomain="Chefkoch")


def main(session, **kwargs):
	session.open(CKmain)


def plugins(**kwargs):
	return [
		PluginDescriptor(
			name="Chefkoch.de",
			description="Chefkoch.de Rezepte",
			where=[PluginDescriptor.WHERE_PLUGINMENU],
			icon="plugin.png",
			fnc=main,
		),
		PluginDescriptor(
			name="Chefkoch.de",
			description="Chefkoch.de Rezepte",
			where=[PluginDescriptor.WHERE_EXTENSIONSMENU],
			fnc=main,
		),
	]


globals()["Plugins"] = plugins
