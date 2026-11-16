from Plugins.Plugin import PluginDescriptor


def main(session, **kwargs):
	from .ui import CKmain
	session.open(CKmain)


def Plugins(**kwargs):
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
