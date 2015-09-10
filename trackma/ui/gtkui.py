# This file is part of Trackma.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import sys
try:
    import gobject
    import pygtk
    pygtk.require('2.0')
    import gtk
    import pango
except ImportError:
    print ("Couldn't import GTK dependencies. Make sure you "
           "installed the PyGTK package.")
    sys.exit(-1)

gtk.gdk.threads_init() # We'll use threads

import os
import cgi
import time
import threading
import urllib2
from cStringIO import StringIO

try:
    import Image
    imaging_available = True
except ImportError:
    try:
        from PIL import Image
        imaging_available = True
    except ImportError:
        print "Warning: PIL or Pillow isn't available. Preview images will be disabled."
        imaging_available = False

import trackma.messenger as messenger
import trackma.utils as utils

from trackma.engine import Engine
from trackma.accounts import AccountManager

class Trackma_gtk(object):
    engine = None
    config = None
    show_lists = dict()
    image_thread = None
    close_thread = None
    hidden = False
    quit = False

    def main(self):
        """Start the Account Selector"""
        self.configfile = utils.get_root_filename('ui-gtk.json')
        self.config = utils.parse_config(self.configfile, utils.gtk_defaults)

        manager = AccountManager()

        # Use the remembered account if there's one
        if manager.get_default():
            self.start(manager.get_default())
        else:
            self.accountsel = AccountSelect(manager)
            self.accountsel.use_button.connect("clicked", self.use_account)
            self.accountsel.create()

        gtk.main()

    def do_switch_account(self, widget, switch=True):
        manager = AccountManager()
        self.accountsel = AccountSelect(manager = AccountManager(), switch=switch)
        self.accountsel.use_button.connect("clicked", self.use_account)
        self.accountsel.create()

    def use_account(self, widget):
        """Start the main application with the following account"""
        accountid = self.accountsel.get_selected_id()
        account = self.accountsel.manager.get_account(accountid)
        # If remember box is checked, set as default account
        if self.accountsel.is_remember():
            self.accountsel.manager.set_default(accountid)
        else:
            self.accountsel.manager.set_default(None)

        self.accountsel.destroy()

        # Reload the engine if already started,
        # start it otherwise
        if self.engine and self.engine.loaded:
            self.do_reload(None, account, None)
        else:
            self.start(account)

    def start(self, account):
        """Create the main window"""
        # Create engine
        self.account = account
        self.engine = Engine(account)

        self.main = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.main.set_position(gtk.WIN_POS_CENTER)
        self.main.connect('delete_event', self.delete_event)
        self.main.connect('destroy', self.on_destroy)
        self.main.set_title('Trackma-gtk ' + utils.VERSION)
        gtk.window_set_default_icon_from_file(utils.datadir + '/data/icon.png')

        # Menus
        mb_show = gtk.Menu()
        self.mb_play = gtk.ImageMenuItem(gtk.STOCK_MEDIA_PLAY)
        self.mb_play.connect("activate", self.do_play, True)
        mb_scanlibrary = gtk.MenuItem('Re-scan library')
        mb_scanlibrary.connect("activate", self.do_scanlibrary)
        self.mb_info = gtk.MenuItem('Show details...')
        self.mb_info.connect("activate", self.do_info)
        mb_web = gtk.MenuItem("Open web site")
        mb_web.connect("activate", self.do_web)
        mb_copy = gtk.MenuItem("Copy title to clipboard")
        mb_copy.connect("activate", self.do_copytoclip)
        mb_alt_title = gtk.MenuItem("Set alternate title...")
        mb_alt_title.connect("activate", self.do_altname)
        self.mb_delete = gtk.ImageMenuItem(gtk.STOCK_DELETE)
        self.mb_delete.connect("activate", self.do_delete)
        self.mb_exit = gtk.ImageMenuItem(gtk.STOCK_QUIT)
        self.mb_exit.connect("activate", self.do_quit, None)
        gtk.stock_add([(gtk.STOCK_ADD, "Add/Search Shows", 0, 0, "")])
        self.mb_addsearch = gtk.ImageMenuItem(gtk.STOCK_ADD)
        self.mb_addsearch.connect("activate", self.do_addsearch)

        mb_show.append(self.mb_addsearch)
        mb_show.append(gtk.SeparatorMenuItem())
        mb_show.append(self.mb_play)
        mb_show.append(self.mb_info)
        mb_show.append(mb_web)
        mb_show.append(gtk.SeparatorMenuItem())
        mb_show.append(mb_copy)
        mb_show.append(mb_alt_title)
        mb_show.append(gtk.SeparatorMenuItem())
        mb_show.append(self.mb_delete)
        mb_show.append(gtk.SeparatorMenuItem())
        mb_show.append(self.mb_exit)

        mb_list = gtk.Menu()
        gtk.stock_add([(gtk.STOCK_REFRESH, "Sync", 0, 0, "")])
        self.mb_sync = gtk.ImageMenuItem(gtk.STOCK_REFRESH)
        self.mb_sync.connect("activate", self.do_sync)
        self.mb_retrieve = gtk.ImageMenuItem("Retrieve list")
        self.mb_retrieve.connect("activate", self.do_retrieve_ask)
        self.mb_send = gtk.MenuItem('Send changes')
        self.mb_send.connect("activate", self.do_send)

        mb_list.append(self.mb_sync)
        mb_list.append(gtk.SeparatorMenuItem())
        mb_list.append(self.mb_retrieve)
        mb_list.append(self.mb_send)
        mb_list.append(gtk.SeparatorMenuItem())
        mb_list.append(mb_scanlibrary)

        mb_options = gtk.Menu()
        self.mb_switch_account = gtk.MenuItem('Switch Account...')
        self.mb_switch_account.connect("activate", self.do_switch_account)
        self.mb_settings = gtk.MenuItem('Global Settings...')
        self.mb_settings.connect("activate", self.do_settings)

        mb_options.append(self.mb_switch_account)
        mb_options.append(gtk.SeparatorMenuItem())
        mb_options.append(self.mb_settings)

        self.mb_mediatype_menu = gtk.Menu()

        mb_help = gtk.Menu()
        mb_about = gtk.ImageMenuItem(gtk.STOCK_ABOUT)
        mb_about.connect("activate", self.on_about)
        mb_help.append(mb_about)

        # Root menubar
        root_menu1 = gtk.MenuItem("Show")
        root_menu1.set_submenu(mb_show)
        root_list = gtk.MenuItem("List")
        root_list.set_submenu(mb_list)
        root_options = gtk.MenuItem("Options")
        root_options.set_submenu(mb_options)
        mb_mediatype = gtk.MenuItem("Mediatype")
        mb_mediatype.set_submenu(self.mb_mediatype_menu)
        root_menu2 = gtk.MenuItem("Help")
        root_menu2.set_submenu(mb_help)

        mb = gtk.MenuBar()
        mb.append(root_menu1)
        mb.append(root_list)
        mb.append(mb_mediatype)
        mb.append(root_options)
        mb.append(root_menu2)

        # Create vertical box
        vbox = gtk.VBox(False, 0)
        self.main.add(vbox)

        vbox.pack_start(mb, False, False, 0)

        self.top_hbox = gtk.HBox(False, 10)
        self.top_hbox.set_border_width(5)

        self.show_image = ImageView(100, 149)
        self.top_hbox.pack_start(self.show_image, False, False, 0)

        # Right box
        top_right_box = gtk.VBox(False, 0)

        # Line 1: Title
        line1 = gtk.HBox(False, 5)
        self.show_title = gtk.Label()
        self.show_title.set_use_markup(True)
        self.show_title.set_alignment(0, 0.5)
        self.show_title.set_ellipsize(pango.ELLIPSIZE_END)

        line1.pack_start(self.show_title, True, True, 0)

        # API info
        api_hbox = gtk.HBox(False, 5)
        self.api_icon = gtk.Image()
        self.api_user = gtk.Label()
        api_hbox.pack_start(self.api_icon)
        api_hbox.pack_start(self.api_user)

        alignment1 = gtk.Alignment(xalign=1, yalign=0)
        alignment1.add(api_hbox)
        line1.pack_start(alignment1, False, False, 0)

        top_right_box.pack_start(line1, True, True, 0)

        # Line 2: Episode
        line2 = gtk.HBox(False, 5)
        line2_t = gtk.Label('  Progress')
        line2_t.set_size_request(70, -1)
        line2_t.set_alignment(0, 0.5)
        line2.pack_start(line2_t, False, False, 0)
        self.show_ep_num = gtk.SpinButton()
        self.show_ep_num.set_sensitive(False)
        self.show_ep_num.connect("activate", self.do_update)
        #self.show_ep_num.connect("value_changed", self.do_update)
        line2.pack_start(self.show_ep_num, False, False, 0)

        # Buttons
        top_buttons = gtk.HBox(False, 5)

        self.add_epp_button = gtk.Button('+')
        self.add_epp_button.connect("clicked", self.do_add_epp)
        self.add_epp_button.set_sensitive(False)
        line2.pack_start(self.add_epp_button, False, False, 0)

        self.rem_epp_button = gtk.Button('-')
        self.rem_epp_button.connect("clicked", self.do_rem_epp)
        self.rem_epp_button.set_sensitive(False)
        line2.pack_start(self.rem_epp_button, False, False, 0)

        self.update_button = gtk.Button('Update')
        self.update_button.connect("clicked", self.do_update)
        self.update_button.set_sensitive(False)
        line2.pack_start(self.update_button, False, False, 0)

        self.play_button = gtk.Button('Play')
        self.play_button.connect("clicked", self.do_play, False)
        self.play_button.set_sensitive(False)
        line2.pack_start(self.play_button, False, False, 0)

        self.play_next_button = gtk.Button('Play Next')
        self.play_next_button.connect("clicked", self.do_play, True)
        self.play_next_button.set_sensitive(False)
        line2.pack_start(self.play_next_button, False, False, 0)

        top_right_box.pack_start(line2, True, False, 0)

        # Line 3: Score
        line3 = gtk.HBox(False, 5)
        line3_t = gtk.Label('  Score')
        line3_t.set_size_request(70, -1)
        line3_t.set_alignment(0, 0.5)
        line3.pack_start(line3_t, False, False, 0)
        self.show_score = gtk.SpinButton()
        self.show_score.set_adjustment(gtk.Adjustment(upper=10, step_incr=1))
        self.show_score.set_sensitive(False)
        self.show_score.connect("activate", self.do_score)
        line3.pack_start(self.show_score, False, False, 0)

        self.scoreset_button = gtk.Button('Set')
        self.scoreset_button.connect("clicked", self.do_score)
        self.scoreset_button.set_sensitive(False)
        line3.pack_start(self.scoreset_button, False, False, 0)

        top_right_box.pack_start(line3, True, False, 0)

        # Line 4: Status
        line4 = gtk.HBox(False, 5)
        line4_t = gtk.Label('  Status')
        line4_t.set_size_request(70, -1)
        line4_t.set_alignment(0, 0.5)
        line4.pack_start(line4_t, False, False, 0)

        self.statusmodel = gtk.ListStore(str, str)

        self.statusbox = gtk.ComboBox(self.statusmodel)
        cell = gtk.CellRendererText()
        self.statusbox.pack_start(cell, True)
        self.statusbox.add_attribute(cell, 'text', 1)
        self.statusbox_handler = self.statusbox.connect("changed", self.do_status)
        self.statusbox.set_sensitive(False)

        alignment = gtk.Alignment(xalign=0, yalign=0.5)
        alignment.add(self.statusbox)

        line4.pack_start(alignment, True, True, 0)

        top_right_box.pack_start(line4, True, False, 0)

        self.top_hbox.pack_start(top_right_box, True, True, 0)
        vbox.pack_start(self.top_hbox, False, False, 0)

        # Notebook for lists
        self.notebook = gtk.Notebook()
        self.notebook.set_tab_pos(gtk.POS_TOP)
        self.notebook.set_scrollable(True)
        self.notebook.set_border_width(3)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.set_size_request(550, 300)
        sw.set_border_width(5)
        self.notebook.append_page(sw, gtk.Label("Status"))

        vbox.pack_start(self.notebook, True, True, 0)

        self.statusbar = gtk.Statusbar()
        self.statusbar.push(0, 'Trackma-gtk ' + utils.VERSION)
        vbox.pack_start(self.statusbar, False, False, 0)

        vbox.show_all()

        # Accelerators
        accelgrp = gtk.AccelGroup()

        key, mod = gtk.accelerator_parse("<Control>N")
        self.mb_play.add_accelerator("activate", accelgrp, key, mod, gtk.ACCEL_VISIBLE)
        key, mod = gtk.accelerator_parse("<Control>A")
        self.mb_addsearch.add_accelerator("activate", accelgrp, key, mod, gtk.ACCEL_VISIBLE)
        key, mod = gtk.accelerator_parse("<Control>S")
        self.mb_sync.add_accelerator("activate", accelgrp, key, mod, gtk.ACCEL_VISIBLE)
        key, mod = gtk.accelerator_parse("<Control>E")
        self.mb_send.add_accelerator("activate", accelgrp, key, mod, gtk.ACCEL_VISIBLE)
        key, mod = gtk.accelerator_parse("<Control>R")
        self.mb_retrieve.add_accelerator("activate", accelgrp, key, mod, gtk.ACCEL_VISIBLE)
        key, mod = gtk.accelerator_parse("<Control>Right")
        self.add_epp_button.add_accelerator("activate", accelgrp, key, mod, gtk.ACCEL_VISIBLE)
        self.add_epp_button.set_tooltip_text("Ctrl+Right")
        key, mod = gtk.accelerator_parse("<Control>Left")
        self.rem_epp_button.add_accelerator("activate", accelgrp, key, mod, gtk.ACCEL_VISIBLE)
        self.rem_epp_button.set_tooltip_text("Ctrl+Left")

        self.main.add_accel_group(accelgrp)

        # Status icon
        self.statusicon = gtk.StatusIcon()
        self.statusicon.set_from_file(utils.datadir + '/data/icon.png')
        self.statusicon.set_tooltip('Trackma-gtk ' + utils.VERSION)
        self.statusicon.connect('activate', self.status_event)
        self.statusicon.connect('popup-menu', self.status_menu_event)
        if self.config['show_tray']:
            self.statusicon.set_visible(True)
        else:
            self.statusicon.set_visible(False)

        # Engine configuration
        self.engine.set_message_handler(self.message_handler)
        self.engine.connect_signal('episode_changed', self.changed_show)
        self.engine.connect_signal('score_changed', self.changed_show)
        self.engine.connect_signal('status_changed', self.changed_show_status)
        self.engine.connect_signal('playing', self.playing_show)
        self.engine.connect_signal('show_added', self.changed_show_status)
        self.engine.connect_signal('show_deleted', self.changed_show_status)
        self.engine.connect_signal('prompt_for_update', self.do_update_next)

        self.selected_show = 0

        if not imaging_available:
            self.show_image.pholder_show("PIL library\nnot available")

        self.allow_buttons(False)

        # Don't show the main dialog if start in tray option is set
        if self.config['show_tray'] and self.config['start_in_tray']:
            self.hidden = True
        else:
            self.main.show()

        self.start_engine()

    def _clear_gui(self):
        self.show_title.set_text('<span size="14000"><b>Trackma</b></span>')
        self.show_title.set_use_markup(True)
        self.show_image.pholder_show("Trackma")

        current_api = utils.available_libs[self.account['api']]
        api_iconfile = current_api[1]

        self.main.set_title('Trackma-gtk %s [%s (%s)]' % (
            utils.VERSION,
            self.engine.api_info['name'],
            self.engine.api_info['mediatype']))
        self.api_icon.set_from_file(api_iconfile)
        self.api_user.set_text("%s (%s)" % (
            self.engine.get_userconfig('username'),
            self.engine.api_info['mediatype']))

        self.score_decimal_places = 0
        if isinstance( self.engine.mediainfo['score_step'], float ):
            self.score_decimal_places = len(str(self.engine.mediainfo['score_step']).split('.')[1])

        self.show_score.set_value(0)
        self.show_score.set_digits(self.score_decimal_places)
        self.show_score.set_range(0, self.engine.mediainfo['score_max'])
        self.show_score.get_adjustment().set_step_increment(self.engine.mediainfo['score_step'])

        can_play = self.engine.mediainfo['can_play']
        can_update = self.engine.mediainfo['can_update']

        self.play_button.set_sensitive(can_play)
        self.play_next_button.set_sensitive(can_play)

        self.update_button.set_sensitive(can_update)
        self.show_ep_num.set_sensitive(can_update)
        self.add_epp_button.set_sensitive(can_update)

    def _create_lists(self):
        statuses_nums = self.engine.mediainfo['statuses']
        statuses_names = self.engine.mediainfo['statuses_dict']

        # Statusbox
        self.statusmodel.clear()
        for status in statuses_nums:
            self.statusmodel.append([status, statuses_names[status]])
        self.statusbox.set_model(self.statusmodel)
        self.statusbox.show_all()

        # Clear notebook
        for i in xrange(self.notebook.get_n_pages()):
            self.notebook.remove_page(-1)

        # Insert pages
        for status in statuses_nums:
            name = statuses_names[status]

            sw = gtk.ScrolledWindow()
            sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
            sw.set_size_request(550, 300)
            sw.set_border_width(5)

            self.show_lists[status] = ShowView(
                    status,
                    self.engine.mediainfo['has_progress'],
                    self.score_decimal_places)
            self.show_lists[status].get_selection().connect("changed", self.select_show)
            self.show_lists[status].connect("row-activated", self.do_info)
            self.show_lists[status].connect("button-press-event", self.showview_context_menu)
            self.show_lists[status].pagenumber = self.notebook.get_n_pages()
            sw.add(self.show_lists[status])

            self.notebook.append_page(sw, gtk.Label(name))
            self.notebook.show_all()
            self.show_lists[status].realize()

        self.notebook.connect("switch-page", self.select_show)

    def idle_destroy(self):
        gobject.idle_add(self.idle_destroy_push)

    def idle_destroy_push(self):
        self.quit = True
        self.main.destroy()

    def idle_restart(self):
        gobject.idle_add(self.idle_restart_push)

    def idle_restart_push(self):
        self.quit = False
        self.main.destroy()
        self.do_switch_account(None, False)

    def on_destroy(self, widget):
        if self.quit:
            gtk.main_quit()

    def status_event(self, widget):
        # Called when the tray icon is left-clicked
        if self.hidden:
            self.main.show()
            self.hidden = False
        else:
            self.main.hide()
            self.hidden = True

    def status_menu_event(self, icon, button, time):
        # Called when the tray icon is right-clicked
        menu = gtk.Menu()
        mb_show = gtk.MenuItem("Show/Hide")
        mb_about = gtk.ImageMenuItem(gtk.STOCK_ABOUT)
        mb_quit = gtk.ImageMenuItem(gtk.STOCK_QUIT)

        mb_show.connect("activate", self.status_event)
        mb_about.connect("activate", self.on_about)
        mb_quit.connect("activate", self.do_quit)

        menu.append(mb_show)
        menu.append(mb_about)
        menu.append(gtk.SeparatorMenuItem())
        menu.append(mb_quit)
        menu.show_all()

        menu.popup(None, None, gtk.status_icon_position_menu, button, time, self.statusicon)

    def delete_event(self, widget, event, data=None):
        if self.statusicon.get_visible() and self.config['close_to_tray']:
            self.hidden = True
            self.main.hide()
        else:
            self.do_quit()
        return True

    def do_quit(self, widget=None, event=None, data=None):
        if self.close_thread is None:
            self.close_thread = threading.Thread(target=self.task_unload).start()

    def do_addsearch(self, widget):
        win = ShowSearch(self.engine)
        win.show_all()

    def do_settings(self, widget):
        win = Settings(self.engine, self.config, self.configfile)
        win.show_all()

    def do_reload(self, widget, account, mediatype):
        self.selected_show = 0

        threading.Thread(target=self.task_reload, args=[account, mediatype]).start()

    def do_play(self, widget, playnext, ep=None):
        threading.Thread(target=self.task_play, args=(playnext,ep)).start()

    def do_scanlibrary(self, widget):
        threading.Thread(target=self.task_scanlibrary).start()

    def do_delete(self, widget):
        try:
            show = self.engine.get_show_info(self.selected_show)
            self.engine.delete_show(show)
        except utils.TrackmaError, e:
            self.error(e.message)

    def do_info(self, widget, d1=None, d2=None):
        show = self.engine.get_show_info(self.selected_show)
        win = InfoDialog(self.engine, show)

    def do_add_epp(self, widget):
        ep = self.show_ep_num.get_value_as_int()
        try:
            show = self.engine.set_episode(self.selected_show, ep + 1)
            self.show_ep_num.set_value(show['my_progress'])
        except utils.TrackmaError, e:
            self.error(e.message)

    def do_rem_epp(self, widget):
        ep = self.show_ep_num.get_value_as_int()
        try:
            if(ep > 0):
                    show = self.engine.set_episode(self.selected_show, ep - 1)
                    self.show_ep_num.set_value(show['my_progress'])

        except utils.TrackmaError, e:
            self.error(e.message)

    def do_update(self, widget):
        self.show_ep_num.update()
        ep = self.show_ep_num.get_value_as_int()
        try:
            show = self.engine.set_episode(self.selected_show, ep)
        except utils.TrackmaError, e:
            self.error(e.message)

    def do_score(self, widget):
        self.show_score.update()
        score = self.show_score.get_value()
        try:
            show = self.engine.set_score(self.selected_show, score)
        except utils.TrackmaError, e:
            self.error(e.message)

    def do_status(self, widget):
        statusiter = self.statusbox.get_active_iter()
        status = self.statusmodel.get(statusiter, 0)[0]

        try:
            show = self.engine.set_status(self.selected_show, status)
        except utils.TrackmaError, e:
            self.error(e.message)

    def do_update_next(self, show, played_ep):
        # Thread safe
        gobject.idle_add(self.task_update_next, show, played_ep)

    def changed_show(self, show):
        status = show['my_status']
        self.show_lists[status].update(show)

    def changed_show_title(self, show, altname):
        status = show['my_status']
        self.show_lists[status].update_title(show, altname)

    def changed_show_status(self, show, old_status=None):
        # Rebuild lists
        status = show['my_status']

        self.build_list(status)
        if old_status:
            self.build_list(old_status)

        pagenumber = self.show_lists[status].pagenumber
        self.notebook.set_current_page(pagenumber)

        self.show_lists[status].select(show)

    def playing_show(self, show, is_playing, episode):
        status = show['my_status']
        self.show_lists[status].playing(show, is_playing)

    def task_update_next(self, show, played_ep):
        dialog = gtk.MessageDialog(self.main,
                    gtk.DIALOG_MODAL,
                    gtk.MESSAGE_QUESTION,
                    gtk.BUTTONS_YES_NO,
                    "Update %s to episode %d?" % (show['title'], played_ep))
        dialog.show_all()
        dialog.connect("response", self.task_update_next_response, show, played_ep)

    def task_update_next_response(self, widget, response, show, played_ep):
        widget.destroy()
        # Update show to the played episode
        if response == gtk.RESPONSE_YES:
            try:
                show = self.engine.set_episode(show['id'], played_ep)
                status = show['my_status']
                self.show_lists[status].update(show)
            except utils.TrackmaError, e:
                self.error(e.message)

    def task_play(self, playnext, ep):
        self.allow_buttons(False)

        show = self.engine.get_show_info(self.selected_show)

        try:
            if playnext:
                self.engine.play_episode(show)
            else:
                if not ep:
                    ep = self.show_ep_num.get_value_as_int()
                self.engine.play_episode(show, ep)
        except utils.TrackmaError, e:
            self.error(e.message)

        self.status("Ready.")
        self.allow_buttons(True)

    def task_scanlibrary(self):
        self.allow_buttons(False)

        try:
            result = self.engine.scan_library()
        except utils.TrackmaError, e:
            self.error(e.message)

        gobject.idle_add(self.build_list, self.engine.mediainfo['status_start'])

        self.status("Ready.")
        self.allow_buttons(True)

    def task_unload(self):
        self.allow_buttons(False)
        self.engine.unload()

        self.idle_destroy()

    def do_retrieve_ask(self, widget):
        queue = self.engine.get_queue()

        if len(queue) > 0:
            dialog = gtk.MessageDialog(self.main,
                gtk.DIALOG_MODAL,
                gtk.MESSAGE_QUESTION,
                gtk.BUTTONS_YES_NO,
                "There are %d queued changes in your list. If you retrieve the remote list now you will lose your queued changes. Are you sure you want to continue?" % len(queue))
            dialog.show_all()
            dialog.connect("response", self.do_retrieve)
        else:
            # If the user doesn't have any queued changes
            # just go ahead
            self.do_retrieve()

    def do_retrieve(self, widget=None, response=gtk.RESPONSE_YES):
        if widget:
            widget.destroy()

        if response == gtk.RESPONSE_YES:
            threading.Thread(target=self.task_sync, args=(False,True)).start()

    def do_send(self, widget):
        threading.Thread(target=self.task_sync, args=(True,False)).start()

    def do_sync(self, widget):
        threading.Thread(target=self.task_sync, args=(True,True)).start()

    def task_sync(self, send, retrieve):
        self.allow_buttons(False)

        if send:
            self.engine.list_upload()
        if retrieve:
            self.engine.list_download()

        gobject.idle_add(self.build_all_lists)

        self.status("Ready.")
        self.allow_buttons(True)

    def start_engine(self):
        threading.Thread(target=self.task_start_engine).start()

    def task_start_engine(self):
        if not self.engine.loaded:
            try:
                self.engine.start()
            except utils.TrackmaFatal, e:
                print("Fatal engine error: %s" % e.message)
                self.idle_restart()
                self.error("Fatal engine error: %s" % e.message)
                return

        gtk.threads_enter()
        self.statusbox.handler_block(self.statusbox_handler)
        self._clear_gui()
        self._create_lists()
        self.build_all_lists()

        # Clear and build API and mediatypes menus
        for i in self.mb_mediatype_menu.get_children():
            self.mb_mediatype_menu.remove(i)

        for mediatype in self.engine.api_info['supported_mediatypes']:
            item = gtk.RadioMenuItem(None, mediatype)
            if mediatype == self.engine.api_info['mediatype']:
                item.set_active(True)
            item.connect("activate", self.do_reload, None, mediatype)
            self.mb_mediatype_menu.append(item)
            item.show()

        self.statusbox.handler_unblock(self.statusbox_handler)
        gtk.threads_leave()

        self.status("Ready.")
        self.allow_buttons(True)

    def task_reload(self, account, mediatype):
        try:
            self.engine.reload(account, mediatype)
        except utils.TrackmaError, e:
            self.error(e.message)
        except utils.TrackmaFatal, e:
            print("Fatal engine error: %s" % e.message)
            self.idle_restart()
            self.error("Fatal engine error: %s" % e.message)
            return

        if account:
            self.account = account

        # Refresh the GUI
        self.task_start_engine()

    def select_show(self, widget, page=None, page_num=None):
        page = page_num

        if page is None:
            page = self.notebook.get_current_page()

        selection = self.notebook.get_nth_page(page).get_child().get_selection()

        (tree_model, tree_iter) = selection.get_selected()
        if not tree_iter:
            self.allow_buttons_push(False, lists_too=False)
            return

        try:
            self.selected_show = int(tree_model.get(tree_iter, 0)[0])
        except ValueError:
            self.selected_show = tree_model.get(tree_iter, 0)[0]

        self.allow_buttons_push(True, lists_too=False)

        show = self.engine.get_show_info(self.selected_show)

        # Block handlers
        self.statusbox.handler_block(self.statusbox_handler)

        if self.image_thread is not None:
            self.image_thread.cancel()

        self.show_title.set_text('<span size="14000"><b>{0}</b></span>'.format(cgi.escape(show['title'])))
        self.show_title.set_use_markup(True)

        # Episode selector
        if show['total']:
            adjustment = gtk.Adjustment(upper=show['total'], step_incr=1)
        else:
            adjustment = gtk.Adjustment(upper=1000, step_incr=1)

        self.show_ep_num.set_adjustment(adjustment)
        self.show_ep_num.set_value(show['my_progress'])

        # Status selector
        for i in self.statusmodel:
            if i[0] == str(show['my_status']):
                self.statusbox.set_active_iter(i.iter)
                break

        # Score selector
        self.show_score.set_value(show['my_score'])

        # Image
        if show.get('image_thumb') or show.get('image'):
            utils.make_dir('cache')
            filename = utils.get_filename('cache', "%s.jpg" % (show['id']))

            if os.path.isfile(filename):
                self.show_image.image_show(filename)
            else:
                if imaging_available:
                    self.show_image.pholder_show('Loading...')
                    self.image_thread = ImageTask(self.show_image, show.get('image_thumb') or show['image'], filename, (100, 149))
                    self.image_thread.start()
                else:
                    self.show_image.pholder_show("PIL library\nnot available")

        # Unblock handlers
        self.statusbox.handler_unblock(self.statusbox_handler)

    def build_all_lists(self):
        for status in self.show_lists.iterkeys():
            self.build_list(status)

    def build_list(self, status):
        widget = self.show_lists[status]
        widget.append_start()

        if status == self.engine.mediainfo['status_start']:
            library = self.engine.library()
            for show in self.engine.filter_list(widget.status_filter):
                widget.append(show, self.engine.altname(show['id']), library.get(show['id']))
        else:
            for show in self.engine.filter_list(widget.status_filter):
                widget.append(show, self.engine.altname(show['id']))

        widget.append_finish()

    def on_about(self, widget):
        about = gtk.AboutDialog()
        about.set_program_name("Trackma-gtk")
        about.set_version(utils.VERSION)
        about.set_comments("Trackma is an open source client for media tracking websites.")
        about.set_website("http://github.com/z411/trackma")
        about.set_copyright("(c) z411 - Icon by shuuichi")
        about.run()
        about.destroy()

    def message_handler(self, classname, msgtype, msg):
        # Thread safe
        print "%s: %s" % (classname, msg)
        if msgtype == messenger.TYPE_WARN:
            gobject.idle_add(self.status_push, "%s warning: %s" % (classname, msg))
        elif msgtype != messenger.TYPE_DEBUG:
            gobject.idle_add(self.status_push, "%s: %s" % (classname, msg))

    def error(self, msg, icon=gtk.MESSAGE_ERROR):
        # Thread safe
        gobject.idle_add(self.error_push, msg, icon)

    def error_push(self, msg, icon=gtk.MESSAGE_ERROR):
        dialog = gtk.MessageDialog(self.main, gtk.DIALOG_MODAL, icon, gtk.BUTTONS_OK, msg)
        dialog.show_all()
        dialog.connect("response", self.modal_close)

    def modal_close(self, widget, response_id):
        widget.destroy()

    def status(self, msg):
        # Thread safe
        gobject.idle_add(self.status_push, msg)

    def status_push(self, msg):
        self.statusbar.push(0, msg)

    def allow_buttons(self, boolean):
        # Thread safe
        gobject.idle_add(self.allow_buttons_push, boolean)

    def allow_buttons_push(self, boolean, lists_too=True):
        if lists_too:
            for widget in self.show_lists.itervalues():
                widget.set_sensitive(boolean)

        if self.selected_show or not boolean:
            if self.engine.mediainfo['can_play']:
                self.play_button.set_sensitive(boolean)
                self.play_next_button.set_sensitive(boolean)

            if self.engine.mediainfo['can_update']:
                self.update_button.set_sensitive(boolean)
                self.show_ep_num.set_sensitive(boolean)
                self.add_epp_button.set_sensitive(boolean)
                self.rem_epp_button.set_sensitive(boolean)

            self.scoreset_button.set_sensitive(boolean)
            self.show_score.set_sensitive(boolean)
            self.statusbox.set_sensitive(boolean)

    def do_copytoclip(self, widget):
        # Copy selected show title to clipboard
        show = self.engine.get_show_info(self.selected_show)

        clipboard = gtk.clipboard_get()
        clipboard.set_text(show['title'])

        self.status('Title copied to clipboard.')

    def do_altname(self,widget):
        show = self.engine.get_show_info(self.selected_show)
        current_altname = self.engine.altname(self.selected_show)

        dialog = gtk.MessageDialog(
            None,
            gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
            gtk.MESSAGE_QUESTION,
            gtk.BUTTONS_OK_CANCEL,
            None)
        dialog.set_markup('Set the <b>alternate title</b> for the show.')
        entry = gtk.Entry()
        entry.set_text(current_altname)
        entry.connect("activate", self.altname_response, dialog, gtk.RESPONSE_OK)
        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label("Alternate Title:"), False, 5, 5)
        hbox.pack_end(entry)
        dialog.format_secondary_markup("Use this if the tracker is unable to find this show. Leave blank to disable.")
        dialog.vbox.pack_end(hbox, True, True, 0)
        dialog.show_all()
        retval = dialog.run()

        if retval == gtk.RESPONSE_OK:
            text = entry.get_text()
            self.engine.altname(self.selected_show, text)
            self.changed_show_title(show, text)

        dialog.destroy()

    def altname_response(self, entry, dialog, response):
        dialog.response(response)

    def do_web(self, widget):
        show = self.engine.get_show_info(self.selected_show)
        if show['url']:
            gtk.show_uri(None, show['url'], gtk.gdk.CURRENT_TIME)

    def showview_context_menu(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            pthinfo = treeview.get_path_at_pos(x, y)
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)
                show = self.engine.get_show_info(self.selected_show)

                menu = gtk.Menu()
                mb_play = gtk.ImageMenuItem(gtk.STOCK_MEDIA_PLAY)
                mb_play.connect("activate", self.do_play, True)
                mb_info = gtk.MenuItem("Show details...")
                mb_info.connect("activate", self.do_info)
                mb_web = gtk.MenuItem("Open web site")
                mb_web.connect("activate", self.do_web)
                mb_copy = gtk.MenuItem("Copy title to clipboard")
                mb_copy.connect("activate", self.do_copytoclip)
                mb_alt_title = gtk.MenuItem("Set alternate title...")
                mb_alt_title.connect("activate", self.do_altname)
                mb_delete = gtk.ImageMenuItem(gtk.STOCK_DELETE)
                mb_delete.connect("activate", self.do_delete)

                menu.append(mb_play)

                if show['total']:
                    menu_eps = gtk.Menu()
                    for i in xrange(1, show['total'] + 1):
                        mb_playep = gtk.MenuItem(str(i))
                        mb_playep.connect("activate", self.do_play, False, i)
                        menu_eps.append(mb_playep)
                    mb_playep = gtk.MenuItem("Play episode")
                    mb_playep.set_submenu(menu_eps)
                    menu.append(mb_playep)

                menu.append(mb_info)
                menu.append(mb_web)
                menu.append(gtk.SeparatorMenuItem())
                menu.append(mb_copy)
                menu.append(mb_alt_title)
                menu.append(gtk.SeparatorMenuItem())
                menu.append(mb_delete)

                menu.show_all()
                menu.popup(None, None, None, event.button, event.time)

class ImageTask(threading.Thread):
    cancelled = False

    def __init__(self, show_image, remote, local, size=None):
        self.show_image = show_image
        self.remote = remote
        self.local = local
        self.size = size
        threading.Thread.__init__(self)

    def run(self):
        self.cancelled = False

        time.sleep(1)

        if self.cancelled:
            return

        # If there's a better solution for this please tell me/implement it.

        # If there's a size specified, thumbnail with PIL library
        # otherwise download and save it as it is
        req = urllib2.Request(self.remote)
        req.add_header("User-agent", "TrackmaImage/{}".format(utils.VERSION))
        img_file = StringIO(urllib2.urlopen(req).read())
        if self.size:
            im = Image.open(img_file)
            im.thumbnail((self.size[0], self.size[1]), Image.ANTIALIAS)
            im.save(self.local)
        else:
            with open(self.local, 'wb') as f:
                f.write(img_file.read())

        if self.cancelled:
            return

        gtk.threads_enter()
        self.show_image.image_show(self.local)
        gtk.threads_leave()

    def cancel(self):
        self.cancelled = True

class ImageView(gtk.HBox):
    def __init__(self, w, h):
        gtk.HBox.__init__(self)

        self.showing_pholder = False

        self.w_image = gtk.Image()
        self.w_image.set_size_request(w, h)

        self.w_pholder = gtk.Label()
        self.w_pholder.set_size_request(w, h)

        self.pack_start(self.w_image, False, False, 0)

    def image_show(self, filename):
        if self.showing_pholder:
            self.remove(self.w_pholder)
            self.pack_start(self.w_image, False, False, 0)
            self.w_image.show()
            self.showing_pholder = False

        self.w_image.set_from_file(filename)

    def pholder_show(self, msg):
        if not self.showing_pholder:
            self.pack_end(self.w_pholder, False, False, 0)
            self.remove(self.w_image)
            self.w_pholder.show()
            self.showing_pholder = True

        self.w_pholder.set_text(msg)

class ShowView(gtk.TreeView):
    def __init__(self, status, has_progress=True, decimals=0):
        gtk.TreeView.__init__(self)

        self.has_progress = has_progress
        self.decimals = decimals
        self.status_filter = status

        self.set_enable_search(True)
        self.set_search_column(1)

        self.cols = dict()
        if has_progress:
            columns = (('Title', 1), ('Progress', 2), ('Score', 3), ('Percent', 4))
        else:
            columns = (('Title', 1), ('Score', 3))

        for (name, sort) in columns:
            self.cols[name] = gtk.TreeViewColumn(name)
            self.cols[name].set_sort_column_id(sort)
            self.append_column(self.cols[name])

        #renderer_id = gtk.CellRendererText()
        #self.cols['ID'].pack_start(renderer_id, False)
        #self.cols['ID'].set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        #self.cols['ID'].set_expand(False)
        #self.cols['ID'].add_attribute(renderer_id, 'text', 0)

        renderer_title = gtk.CellRendererText()
        self.cols['Title'].pack_start(renderer_title, False)
        self.cols['Title'].set_resizable(True)
        self.cols['Title'].set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.cols['Title'].set_expand(True)
        self.cols['Title'].add_attribute(renderer_title, 'text', 1)
        self.cols['Title'].add_attribute(renderer_title, 'foreground', 9)

        if has_progress:
            renderer_progress = gtk.CellRendererText()
            self.cols['Progress'].pack_start(renderer_progress, False)
            self.cols['Progress'].add_attribute(renderer_progress, 'text', 4)
            self.cols['Progress'].set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.cols['Progress'].set_expand(False)

            #renderer_percent = gtk.CellRendererProgress()
            renderer_percent = ProgressCellRenderer()
            self.cols['Percent'].pack_start(renderer_percent, False)
            self.cols['Percent'].add_attribute(renderer_percent, 'value', 2)
            self.cols['Percent'].add_attribute(renderer_percent, 'total', 6)
            self.cols['Percent'].add_attribute(renderer_percent, 'subvalue', 7)
            self.cols['Percent'].add_attribute(renderer_percent, 'eps', 8)
            renderer_percent.set_fixed_size(100, -1)

        renderer_score = gtk.CellRendererText()
        self.cols['Score'].pack_start(renderer_score, False)
        self.cols['Score'].add_attribute(renderer_score, 'text', 5)
        self.cols['Score'].set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        self.cols['Score'].set_expand(False)

        # ID, Title, Episodes, Score, Episodes_str, Score_str, Total, Subvalue, Eps, Color
        self.store = gtk.ListStore(str, str, int, float, str, str, int, int, gobject.TYPE_PYOBJECT, str)
        self.set_model(self.store)

    def _get_color(self, show, eps):
        if show.get('queued'):
            return '#54C571'
        elif eps and max(eps) > show['my_progress']:
            return '#FBB917'
        elif show['status'] == utils.STATUS_AIRING:
            return '#0099cc'
        elif show['status'] == utils.STATUS_NOTYET:
            return '#999900'
        else:
            return None

    def append_start(self):
        self.freeze_child_notify()
        self.store.clear()

    def append(self, show, altname=None, eps=None):
        if self.has_progress:
            episodes_str = "%d / %d" % (show['my_progress'], show['total'])
        else:
            episodes_str = ''

        title_str = show['title']
        if altname:
            title_str += " [%s]" % altname

        score_str = "%0.*f" % (self.decimals, show['my_score'])
        aired_eps = utils.estimate_aired_episodes(show)
        if not aired_eps:
            aired_eps = 0

        if eps:
            available_eps = eps.keys()
        else:
            available_eps = []

        row = [show['id'],
               title_str,
               show['my_progress'],
               show['my_score'],
               episodes_str,
               score_str,
               show['total'],
               aired_eps,
               available_eps,
               self._get_color(show, available_eps)]
        self.store.append(row)

    def append_finish(self):
        self.thaw_child_notify()
        self.store.set_sort_column_id(1, gtk.SORT_ASCENDING)

    def get_showid(self):
        selection = self.get_selection()
        if selection is not None:
            selection.set_mode(gtk.SELECTION_SINGLE)
            (tree_model, tree_iter) = selection.get_selected()
            return tree_model.get(tree_iter, 0)[0]

    def update(self, show):
        for row in self.store:
            if int(row[0]) == show['id']:
                if self.has_progress:
                    episodes_str = "%d / %d" % (show['my_progress'], show['total'])
                    row[2] = show['my_progress']
                    row[4] = episodes_str

                score_str = "%0.*f" % (self.decimals, show['my_score'])

                row[3] = show['my_score']
                row[5] = score_str
                row[9] = self._get_color(show, row[8])
                return

        #print "Warning: Show ID not found in ShowView (%d)" % show['id']

    def update_title(self, show, altname=None):
        for row in self.store:
            if int(row[0]) == show['id']:
                if altname:
                    title_str = "%s [%s]" % (show['title'], altname)
                else:
                    title_str = show['title']

                row[1] = title_str
                return

    def playing(self, show, is_playing):
        # Change the color if the show is currently playing
        for row in self.store:
            if int(row[0]) == show['id']:
                if is_playing:
                    row[9] = '#6C2DC7'
                else:
                    row[9] = self._get_color(show, row[8])
                return

    def select(self, show):
        """Select specified row"""
        for row in self.store:
            if int(row[0]) == show['id']:
                selection = self.get_selection()
                selection.select_iter(row.iter)
                break

class AccountSelect(gtk.Window):
    default = None

    def __init__(self, manager, switch=False):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.use_button = gtk.Button('Switch')
        self.use_button.set_sensitive(False)

        self.manager = manager
        self.switch = switch

    def create(self):
        self.pixbufs = {}
        for (libname, lib) in utils.available_libs.iteritems():
            self.pixbufs[libname] = gtk.gdk.pixbuf_new_from_file(lib[1])

        self.set_position(gtk.WIN_POS_CENTER)
        self.set_title('Select Account')
        self.set_border_width(10)
        self.connect('delete-event', self.on_delete)

        vbox = gtk.VBox(False, 10)

        # Treeview
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.set_size_request(400, 200)

        self.accountlist = gtk.TreeView()

        col_user = gtk.TreeViewColumn('Username')
        col_user.set_expand(True)
        self.accountlist.append_column(col_user)
        col_site = gtk.TreeViewColumn('Site')
        self.accountlist.append_column(col_site)

        renderer_user = gtk.CellRendererText()
        col_user.pack_start(renderer_user, False)
        col_user.add_attribute(renderer_user, 'text', 1)
        renderer_icon = gtk.CellRendererPixbuf()
        col_site.pack_start(renderer_icon, False)
        col_site.add_attribute(renderer_icon, 'pixbuf', 3)
        renderer_site = gtk.CellRendererText()
        col_site.pack_start(renderer_site, False)
        col_site.add_attribute(renderer_site, 'text', 2)

        self.store = gtk.ListStore(int, str, str, gtk.gdk.Pixbuf, bool)
        self.accountlist.set_model(self.store)

        self.accountlist.get_selection().connect("changed", self.on_account_changed)
        self.accountlist.connect("row-activated", self.on_row_activated)

        # Bottom buttons
        alignment = gtk.Alignment(xalign=1.0)
        bottombar = gtk.HBox(False, 5)

        self.remember = gtk.CheckButton('Remember')
        if self.manager.get_default() is not None:
            self.remember.set_active(True)
        gtk.stock_add([(gtk.STOCK_APPLY, "Add", 0, 0, "")])
        add_button = gtk.Button(stock=gtk.STOCK_APPLY)
        add_button.connect("clicked", self.do_add)
        self.delete_button = gtk.Button(stock=gtk.STOCK_DELETE)
        self.delete_button.set_sensitive(False)
        self.delete_button.connect("clicked", self.do_delete)
        close_button = gtk.Button(stock=gtk.STOCK_CLOSE)
        close_button.connect("clicked", self.do_close)

        bottombar.pack_start(self.remember, False, False, 0)
        bottombar.pack_start(self.use_button, False, False, 0)
        bottombar.pack_start(add_button, False, False, 0)
        bottombar.pack_start(self.delete_button, False, False, 0)
        bottombar.pack_start(close_button, False, False, 0)
        alignment.add(bottombar)

        sw.add(self.accountlist)

        vbox.pack_start(sw, True, True, 0)
        vbox.pack_start(alignment, False, False, 0)
        self.add(vbox)

        self._refresh_list()
        self.show_all()

    def _refresh_list(self):
        self.store.clear()
        for k, account in self.manager.get_accounts():
            libname = account['api']
            try:
                api = utils.available_libs[libname]
                self.store.append([k, account['username'], api[0], self.pixbufs[libname], True])
            except KeyError:
                # Invalid API
                self.store.append([k, account['username'], 'N/A', None, False])


    def is_remember(self):
        # Return the state of the checkbutton if there's no default account
        if self.default is None:
            return self.remember.get_active()
        else:
            return True

    def get_selected(self):
        selection = self.accountlist.get_selection()
        selection.set_mode(gtk.SELECTION_SINGLE)
        return selection.get_selected()

    def get_selected_id(self):
        if self.default is not None:
            return self.default
        else:
            tree_model, tree_iter = self.get_selected()
            return tree_model.get_value(tree_iter, 0)

    def on_account_changed(self, widget):
        tree_model, tree_iter = self.get_selected()
        if tree_iter:
            is_selectable = tree_model.get_value(tree_iter, 4)
        else:
            is_selectable = False

        self.use_button.set_sensitive(is_selectable)
        self.delete_button.set_sensitive(True)

    def on_row_activated(self, treeview, iter, path):
        self.use_button.emit("clicked")

    def do_add(self, widget):
        """Create Add Account window"""
        self.add_win = AccountSelectAdd(self.pixbufs)
        self.add_win.add_button.connect("clicked", self.add_account)

    def add_account(self, widget):
        """Closes Add Account window and tells the manager to add
        the account to the database"""
        username =  self.add_win.txt_user.get_text().strip()
        password = self.add_win.txt_passwd.get_text()
        apiiter = self.add_win.cmb_api.get_active_iter()

        if not username:
            self.error('Please enter a username.')
            return
        if not password:
            self.error('Please enter a password.')
            return
        if not apiiter:
            self.error('Please select a website.')
            return

        api = self.add_win.model_api.get(apiiter, 0)[0]
        self.add_win.destroy()

        self.manager.add_account(username, password, api)
        self._refresh_list()

    def do_delete(self, widget):
        selectedid = self.get_selected_id()
        dele = self.manager.delete_account(selectedid)

        self._refresh_list()

    def error(self, msg):
        md = gtk.MessageDialog(None,
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR,
            gtk.BUTTONS_CLOSE, msg)
        md.run()
        md.destroy()

    def modal_close(self, widget, response_id):
        widget.destroy()

    def do_close(self, widget):
        self.destroy()
        if not self.switch:
            gtk.main_quit()

    def on_delete(self, widget, data):
        self.do_close(None)
        return False

class InfoDialog(gtk.Window):
    def __init__(self, engine, show):
        self.engine = engine
        self.show = show

        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_position(gtk.WIN_POS_CENTER)
        self.set_title('Show Details')
        self.set_border_width(10)

        fullbox = gtk.VBox()

        # Info box
        info = InfoWidget(engine)
        info.set_size(600, 500)

        # Bottom line (buttons)
        alignment = gtk.Alignment(xalign=1.0)
        bottombar = gtk.HBox(False, 5)

        web_button = gtk.Button('Open web')
        web_button.connect("clicked", self.do_web)
        close_button = gtk.Button(stock=gtk.STOCK_CLOSE)
        close_button.connect("clicked", self.do_close)

        bottombar.pack_start(web_button, False, False, 0)
        bottombar.pack_start(close_button, False, False, 0)
        alignment.add(bottombar)

        fullbox.pack_start(info)
        fullbox.pack_start(alignment)

        self.add(fullbox)
        self.show_all()

        info.load(show)

    def do_close(self, widget):
        self.destroy()

    def do_web(self, widget):
        if self.show['url']:
            gtk.show_uri(None, self.show['url'], gtk.gdk.CURRENT_TIME)


class InfoWidget(gtk.VBox):
    def __init__(self, engine):
        gtk.VBox.__init__(self)

        self.engine = engine

        # Title line
        self.w_title = gtk.Label('')
        self.w_title.set_ellipsize(pango.ELLIPSIZE_END)

        # Middle line (sidebox)
        eventbox_sidebox = gtk.EventBox()
        self.scrolled_sidebox = gtk.ScrolledWindow()
        self.scrolled_sidebox.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sidebox = gtk.HBox()

        alignment_image = gtk.Alignment(yalign=0.0)
        self.w_image = ImageView(225, 350)
        alignment_image.add(self.w_image)

        self.w_content = gtk.Label()

        sidebox.pack_start(alignment_image, padding=5)
        sidebox.pack_start(self.w_content, padding=5)

        eventbox_sidebox.add(sidebox)

        self.scrolled_sidebox.add_with_viewport(eventbox_sidebox)

        self.pack_start(self.w_title, False, False)
        self.pack_start(self.scrolled_sidebox, padding=5)

    def set_size(self, w, h):
        self.scrolled_sidebox.set_size_request(w, h)

    def load(self, show):
        self.show = show

        # Load image
        imagefile = utils.get_filename('cache', "f_%d.jpg" % show['id'])

        if os.path.isfile(imagefile):
            self.w_image.image_show(imagefile)
        else:
            self.w_image.pholder_show('Loading...')
            self.image_thread = ImageTask(self.w_image, show['image'], imagefile)
            self.image_thread.start()

        # Start info loading thread
        threading.Thread(target=self.task_load).start()

    def task_load(self):
        # Thread to ask the engine for show details

        try:
            self.details = self.engine.get_show_details(self.show)
        except utils.TrackmaError, e:
            self.details = None
            self.details_e = e

        gobject.idle_add(self._done)

    def _done(self):
        if self.details:
            # Put the returned details into the lines VBox
            self.w_title.set_text('<span size="14000"><b>{0}</b></span>'.format(cgi.escape(self.details['title'])))
            self.w_title.set_use_markup(True)

            detail = list()
            for line in self.details['extra']:
                if line[0] and line[1]:
                    detail.append("<b>%s</b>\n%s" % (cgi.escape(str(line[0])), cgi.escape(str(line[1]))))

            self.w_content.set_text("\n\n".join(detail))
            self.w_content.set_use_markup(True)
            self.w_content.set_size_request(340, -1)

            self.show_all()
        else:
            self.w_title.set_text('Error while getting details.')
            if self.details_e:
                self.w_content.set_text(self.details_e.message)

        self.w_content.set_alignment(0, 0)
        self.w_content.set_line_wrap(True)
        self.w_content.set_size_request(340, -1)

class Settings(gtk.Window):
    def __init__(self, engine, config, configfile):
        self.engine = engine

        self.config = config
        self.configfile = configfile

        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.set_position(gtk.WIN_POS_CENTER)
        self.set_title('Global Settings')
        self.set_border_width(10)

        ### Play Next ###
        lbl_player = gtk.Label('Media Player')
        lbl_player.set_size_request(120, -1)
        self.txt_player = gtk.Entry(4096)
        playerbrowse_button = gtk.Button('Browse...')
        playerbrowse_button.connect("clicked", self.do_browse, 'Select player', self.txt_player)

        header0 = gtk.Label()
        header0.set_text('<span size="10000"><b>Play Next</b></span>')
        header0.set_use_markup(True)

        line0 = gtk.HBox(False, 5)
        line0.pack_start(lbl_player, False, False, 0)
        line0.pack_start(self.txt_player, False, False, 0)
        line0.pack_start(playerbrowse_button, False, False, 0)

        ### Tracker ###

        # Labels
        lbl_process = gtk.Label('Process Name')
        lbl_process.set_size_request(120, -1)
        lbl_searchdir = gtk.Label('Library Directory')
        lbl_searchdir.set_size_request(120, -1)
        lbl_tracker_enabled = gtk.Label('Enable Tracker')
        lbl_tracker_enabled.set_size_request(120, -1)
        lbl_tracker_plex_host_port = gtk.Label('Host and Port')
        lbl_tracker_plex_host_port.set_size_request(120, -1)
        lbl_tracker_update_wait = gtk.Label('Wait before update')
        lbl_tracker_update_wait.set_size_request(120, -1)
        lbl_tracker_update_options = gtk.Label('Update options')
        lbl_tracker_update_options.set_size_request(120, -1)

        # Entries
        self.txt_process = gtk.Entry(4096)
        self.txt_searchdir = gtk.Entry(4096)
        self.browse_button = gtk.Button('Browse...')
        self.browse_button.connect("clicked", self.do_browse, 'Select search directory', self.txt_searchdir, True)
        self.chk_tracker_enabled = gtk.CheckButton()
        self.txt_plex_host = gtk.Entry(4096)
        self.txt_plex_port = gtk.Entry(5)
        self.txt_plex_port.set_width_chars(5)
        self.chk_tracker_enabled.connect("toggled", self.tracker_type_sensitive)
        self.spin_tracker_update_wait = gtk.SpinButton(gtk.Adjustment(value=5, lower=0, upper=500, step_incr=1, page_incr=10))
        self.chk_tracker_update_close = gtk.CheckButton('Wait for the player to close')
        self.chk_tracker_update_prompt = gtk.CheckButton('Ask before updating')

        # Radio buttons
        self.rbtn_tracker_local = gtk.RadioButton(None, 'Local')
        self.rbtn_tracker_plex = gtk.RadioButton(self.rbtn_tracker_local, 'Plex Media Server')
        self.rbtn_tracker_plex.connect("toggled", self.tracker_type_sensitive)
        self.rbtn_tracker_local.connect("toggled", self.tracker_type_sensitive)

        # Buttons
        alignment = gtk.Alignment(xalign=0.5)
        bottombar = gtk.HBox(False, 5)
        self.apply_button = gtk.Button(stock=gtk.STOCK_APPLY)
        self.apply_button.connect("clicked", self.do_apply)
        close_button = gtk.Button(stock=gtk.STOCK_CANCEL)
        close_button.connect("clicked", self.do_close)
        bottombar.pack_start(self.apply_button, False, False, 0)
        bottombar.pack_start(close_button, False, False, 0)
        alignment.add(bottombar)

        # HBoxes
        header1 = gtk.Label()
        header1.set_text('<span size="10000"><b>Tracker Options</b></span>')
        header1.set_use_markup(True)

        line1 = gtk.HBox(False, 5)
        line1.pack_start(lbl_searchdir, False, False, 0)
        line1.pack_start(self.txt_searchdir, True, True, 0)
        line1.pack_start(self.browse_button, False, False, 0)

        line2 = gtk.HBox(False, 5)
        line2.pack_start(lbl_process, False, False, 0)
        line2.pack_start(self.txt_process, True, True, 0)

        line7 = gtk.HBox(False, 5)
        line7.pack_start(lbl_tracker_plex_host_port, False, False, 0)
        line7.pack_start(self.txt_plex_host, True, True, 0)
        line7.pack_start(self.txt_plex_port, True, True, 0)

        line3 = gtk.HBox(False, 5)
        line3.pack_start(lbl_tracker_enabled, False, False, 0)
        line3.pack_start(self.chk_tracker_enabled, False, False, 0)
        line3.pack_start(self.rbtn_tracker_local, False, False, 0)
        line3.pack_start(self.rbtn_tracker_plex, False, False, 0)

        line8 = gtk.HBox(False, 5)
        line8.pack_start(lbl_tracker_update_wait, False, False, 0)
        line8.pack_start(self.spin_tracker_update_wait, False, False, 0)
        line8.pack_start(gtk.Label('minutes'), False, False, 0)

        line9 = gtk.HBox(False, 5)
        line9.pack_start(lbl_tracker_update_options, False, False, 0)
        line9.pack_start(self.chk_tracker_update_close, False, False, 0)
        line9.pack_start(self.chk_tracker_update_prompt, False, False, 0)

        ### Auto-retrieve ###
        header2 = gtk.Label()
        header2.set_text('<span size="10000"><b>Auto-retrieve</b></span>')
        header2.set_use_markup(True)

        # Radio buttons
        self.rbtn_autoret_off = gtk.RadioButton(None, 'Disabled')
        self.rbtn_autoret_always = gtk.RadioButton(self.rbtn_autoret_off, 'Always at start')

        self.rbtn_autoret_days = gtk.RadioButton(self.rbtn_autoret_off, 'After')
        self.spin_autoret_days = gtk.SpinButton(gtk.Adjustment(value=3, lower=1, upper=100, step_incr=1, page_incr=10))
        self.spin_autoret_days.set_sensitive(False)
        self.rbtn_autoret_days.connect("toggled", self.radio_toggled, self.spin_autoret_days)
        lbl_autoret_days = gtk.Label('days')
        line_autoret_days = gtk.HBox(False, 5)
        line_autoret_days.pack_start(self.rbtn_autoret_days, False, False, 0)
        line_autoret_days.pack_start(self.spin_autoret_days, False, False, 0)
        line_autoret_days.pack_start(lbl_autoret_days, False, False, 0)

        line4 = gtk.VBox(False, 5)
        line4.pack_start(self.rbtn_autoret_off, False, False, 0)
        line4.pack_start(self.rbtn_autoret_always, False, False, 0)
        line4.pack_start(line_autoret_days, False, False, 0)

        ### Auto-send ###
        header3 = gtk.Label()
        header3.set_text('<span size="10000"><b>Auto-send</b></span>')
        header3.set_use_markup(True)

        # Radio buttons
        self.rbtn_autosend_off = gtk.RadioButton(None, 'Disabled')
        self.rbtn_autosend_always = gtk.RadioButton(self.rbtn_autosend_off, 'After every change')
        self.rbtn_autosend_at_exit = gtk.CheckButton('Auto-send at exit')

        self.rbtn_autosend_hours = gtk.RadioButton(self.rbtn_autosend_off, 'After')
        self.spin_autosend_hours = gtk.SpinButton(gtk.Adjustment(value=5, lower=1, upper=1000, step_incr=1, page_incr=10))
        self.spin_autosend_hours.set_sensitive(False)
        self.rbtn_autosend_hours.connect("toggled", self.radio_toggled, self.spin_autosend_hours)
        lbl_autosend_hours = gtk.Label('hours')
        line_autosend_hours = gtk.HBox(False, 5)
        line_autosend_hours.pack_start(self.rbtn_autosend_hours, False, False, 0)
        line_autosend_hours.pack_start(self.spin_autosend_hours, False, False, 0)
        line_autosend_hours.pack_start(lbl_autosend_hours, False, False, 0)

        self.rbtn_autosend_size = gtk.RadioButton(self.rbtn_autosend_off, 'After the queue is larger than')
        self.spin_autosend_size = gtk.SpinButton(gtk.Adjustment(value=5, lower=1, upper=1000, step_incr=1, page_incr=10))
        self.spin_autosend_size.set_sensitive(False)
        self.rbtn_autosend_size.connect("toggled", self.radio_toggled, self.spin_autosend_size)
        lbl_autosend_size = gtk.Label('entries')
        line_autosend_size = gtk.HBox(False, 5)
        line_autosend_size.pack_start(self.rbtn_autosend_size, False, False, 0)
        line_autosend_size.pack_start(self.spin_autosend_size, False, False, 0)
        line_autosend_size.pack_start(lbl_autosend_size, False, False, 0)

        line5 = gtk.VBox(False, 5)
        line5.pack_start(self.rbtn_autosend_off, False, False, 0)
        line5.pack_start(self.rbtn_autosend_always, False, False, 0)
        line5.pack_start(line_autosend_hours, False, False, 0)
        line5.pack_start(line_autosend_size, False, False, 0)
        line5.pack_start(self.rbtn_autosend_at_exit, False, False, 0)


        ### GTK Interface ###
        header4 = gtk.Label()
        header4.set_text('<span size="10000"><b>GTK Interface</b></span>')
        header4.set_use_markup(True)

        self.chk_show_tray = gtk.CheckButton('Show Tray Icon')
        self.chk_close_to_tray = gtk.CheckButton('Close to Tray')
        self.chk_start_in_tray = gtk.CheckButton('Start Minimized to Tray')
        self.chk_close_to_tray.set_sensitive(False)
        self.chk_start_in_tray.set_sensitive(False)
        self.chk_show_tray.connect("toggled", self.radio_toggled, self.chk_close_to_tray)
        self.chk_show_tray.connect("toggled", self.radio_toggled, self.chk_start_in_tray)
        line6 = gtk.VBox(False, 5)
        line6.pack_start(self.chk_show_tray, False, False, 0)
        line6.pack_start(self.chk_close_to_tray, False, False, 0)
        line6.pack_start(self.chk_start_in_tray, False, False, 0)

        # Join HBoxes
        mainbox = gtk.VBox(False, 10)
        notebook = gtk.Notebook()

        page0 = gtk.VBox(False, 10)
        page0.set_border_width(5)
        page0.pack_start(header0, False, False, 0)
        page0.pack_start(line0, False, False, 0)
        page0.pack_start(header1, False, False, 0)
        page0.pack_start(line3, False, False, 0)
        page0.pack_start(line1, False, False, 0)
        page0.pack_start(line2, False, False, 0)
        page0.pack_start(line7, False, False, 0)
        page0.pack_start(line8, False, False, 0)
        page0.pack_start(line9, False, False, 0)

        page1 = gtk.VBox(False, 10)
        page1.set_border_width(5)
        page1.pack_start(header2, False, False, 0)
        page1.pack_start(line4, False, False, 0)
        page1.pack_start(header3, False, False, 0)
        page1.pack_start(line5, False, False, 0)

        page2 = gtk.VBox(False, 10)
        page2.set_border_width(5)
        page2.pack_start(header4, False, False, 0)
        page2.pack_start(line6, False, False, 0)

        notebook.append_page(page0, gtk.Label('Media'))
        notebook.append_page(page1, gtk.Label('Sync'))
        notebook.append_page(page2, gtk.Label('User Interface'))
        mainbox.pack_start(notebook, False, False, 0)
        mainbox.pack_start(alignment, False, False, 0)

        self.add(mainbox)
        self.load_config()

    def load_config(self):
        """Engine Configuration"""
        self.txt_player.set_text(self.engine.get_config('player'))
        self.txt_process.set_text(self.engine.get_config('tracker_process'))
        self.txt_searchdir.set_text(self.engine.get_config('searchdir'))
        self.txt_plex_host.set_text(self.engine.get_config('plex_host'))
        self.txt_plex_port.set_text(self.engine.get_config('plex_port'))
        self.chk_tracker_enabled.set_active(self.engine.get_config('tracker_enabled'))
        self.rbtn_autosend_at_exit.set_active(self.engine.get_config('autosend_at_exit'))
        self.spin_tracker_update_wait.set_value(self.engine.get_config('tracker_update_wait'))
        self.chk_tracker_update_close.set_active(self.engine.get_config('tracker_update_close'))
        self.chk_tracker_update_prompt.set_active(self.engine.get_config('tracker_update_prompt'))

        if self.engine.get_config('tracker_type') == 'local':
            self.rbtn_tracker_local.set_active(True)
            self.txt_plex_host.set_sensitive(False)
            self.txt_plex_port.set_sensitive(False)
        elif self.engine.get_config('tracker_type') == 'plex':
            self.rbtn_tracker_plex.set_active(True)
            self.txt_process.set_sensitive(False)

        if self.engine.get_config('autoretrieve') == 'always':
            self.rbtn_autoret_always.set_active(True)
        elif self.engine.get_config('autoretrieve') == 'days':
            self.rbtn_autoret_days.set_active(True)

        if self.engine.get_config('autosend') == 'always':
            self.rbtn_autosend_always.set_active(True)
        elif self.engine.get_config('autosend') == 'hours':
            self.rbtn_autosend_hours.set_active(True)
        elif self.engine.get_config('autosend') == 'size':
            self.rbtn_autosend_size.set_active(True)

        self.spin_autoret_days.set_value(self.engine.get_config('autoretrieve_days'))
        self.spin_autosend_hours.set_value(self.engine.get_config('autosend_hours'))
        self.spin_autosend_size.set_value(self.engine.get_config('autosend_size'))

        """GTK Interface Configuration"""
        self.chk_show_tray.set_active(self.config['show_tray'])
        self.chk_close_to_tray.set_active(self.config['close_to_tray'])
        self.chk_start_in_tray.set_active(self.config['start_in_tray'])

    def save_config(self):
        """Engine Configuration"""
        self.engine.set_config('player', self.txt_player.get_text())
        self.engine.set_config('tracker_process', self.txt_process.get_text())
        self.engine.set_config('searchdir', self.txt_searchdir.get_text())
        self.engine.set_config('plex_host', self.txt_plex_host.get_text())
        self.engine.set_config('plex_port', self.txt_plex_port.get_text())
        self.engine.set_config('tracker_enabled', self.chk_tracker_enabled.get_active())
        self.engine.set_config('autosend_at_exit', self.rbtn_autosend_at_exit.get_active())
        self.engine.set_config('tracker_update_wait', self.spin_tracker_update_wait.get_value())
        self.engine.set_config('tracker_update_close', self.chk_tracker_update_close.get_active())
        self.engine.set_config('tracker_update_prompt', self.chk_tracker_update_prompt.get_active())

        # Tracker type
        if self.rbtn_tracker_local.get_active():
            self.engine.set_config('tracker_type', 'local')
        elif self.rbtn_tracker_plex.get_active():
            self.engine.set_config('tracker_type', 'plex')

        # Auto-retrieve
        if self.rbtn_autoret_always.get_active():
            self.engine.set_config('autoretrieve', 'always')
        elif self.rbtn_autoret_days.get_active():
            self.engine.set_config('autoretrieve', 'days')
        else:
            self.engine.set_config('autoretrieve', 'off')

        # Auto-send
        if self.rbtn_autosend_always.get_active():
            self.engine.set_config('autosend', 'always')
        elif self.rbtn_autosend_hours.get_active():
            self.engine.set_config('autosend', 'hours')
        elif self.rbtn_autosend_size.get_active():
            self.engine.set_config('autosend', 'size')
        else:
            self.engine.set_config('autosend', 'off')

        self.engine.set_config('autoretrieve_days', self.spin_autoret_days.get_value_as_int())
        self.engine.set_config('autosend_hours', self.spin_autosend_hours.get_value_as_int())
        self.engine.set_config('autosend_size', self.spin_autosend_size.get_value_as_int())

        self.engine.save_config()

        """GTK Interface configuration"""
        self.config['show_tray'] = self.chk_show_tray.get_active()

        if self.chk_show_tray.get_active():
            self.config['close_to_tray'] = self.chk_close_to_tray.get_active()
            self.config['start_in_tray'] = self.chk_start_in_tray.get_active()
        else:
            self.config['close_to_tray'] = False
            self.config['start_in_tray'] = False

        utils.save_config(self.config, self.configfile)

    def radio_toggled(self, widget, spin):
        spin.set_sensitive(widget.get_active())

    def tracker_type_sensitive(self, widget):
        if self.chk_tracker_enabled.get_active():
            if self.rbtn_tracker_local.get_active():
                self.txt_process.set_sensitive(True)
                self.txt_plex_host.set_sensitive(False)
                self.txt_plex_port.set_sensitive(False)
            elif self.rbtn_tracker_plex.get_active():
                self.txt_plex_host.set_sensitive(True)
                self.txt_plex_port.set_sensitive(True)
                self.txt_process.set_sensitive(False)
            self.spin_tracker_update_wait.set_sensitive(True)
        else:
            self.txt_process.set_sensitive(False)
            self.spin_tracker_update_wait.set_sensitive(False)
            self.txt_plex_host.set_sensitive(False)
            self.txt_plex_port.set_sensitive(False)

    def do_browse(self, widget, title, entry, dironly=False):
        browsew = gtk.FileChooserDialog(title,
                                        None,
                                        gtk.FILE_CHOOSER_ACTION_OPEN,
                                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                        gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        browsew.set_default_response(gtk.RESPONSE_OK)

        if dironly:
            browsew.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)

        response = browsew.run()
        if response == gtk.RESPONSE_OK:
            entry.set_text(browsew.get_filename())
        browsew.destroy()

    def do_apply(self, widget):
        self.save_config()
        self.destroy()

    def do_close(self, widget):
        self.destroy()

class AccountSelectAdd(gtk.Window):
    def __init__(self, pixbufs):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.set_position(gtk.WIN_POS_CENTER)
        self.set_title('Create Account')
        self.set_border_width(10)

        # Labels
        self.lbl_user = gtk.Label('Username')
        self.lbl_user.set_size_request(70, -1)
        self.lbl_passwd = gtk.Label('Password')
        self.lbl_passwd.set_size_request(70, -1)
        lbl_api = gtk.Label('Website')
        lbl_api.set_size_request(70, -1)

        # Entries
        self.txt_user = gtk.Entry(128)
        self.txt_passwd = gtk.Entry(128)
        self.txt_passwd.set_visibility(False)

        # Combobox
        self.model_api = gtk.ListStore(str, str, gtk.gdk.Pixbuf)

        for (libname, lib) in sorted(utils.available_libs.iteritems()):
            self.model_api.append([libname, lib[0], pixbufs[libname]])

        self.cmb_api = gtk.ComboBox(self.model_api)
        cell_icon = gtk.CellRendererPixbuf()
        cell_name = gtk.CellRendererText()
        self.cmb_api.pack_start(cell_icon, False)
        self.cmb_api.pack_start(cell_name, True)
        self.cmb_api.add_attribute(cell_icon, 'pixbuf', 2)
        self.cmb_api.add_attribute(cell_name, 'text', 1)
        self.cmb_api.connect("changed", self._refresh)

        # Buttons
        self.btn_auth = gtk.Button("Request PIN")
        self.btn_auth.connect("clicked", self.do_auth)

        alignment = gtk.Alignment(xalign=0.5)
        bottombar = gtk.HBox(False, 5)
        self.add_button = gtk.Button(stock=gtk.STOCK_APPLY)
        close_button = gtk.Button(stock=gtk.STOCK_CLOSE)
        close_button.connect("clicked", self.do_close)
        bottombar.pack_start(self.add_button, False, False, 0)
        bottombar.pack_start(close_button, False, False, 0)
        alignment.add(bottombar)

        # HBoxes
        line1 = gtk.HBox(False, 5)
        line1.pack_start(self.lbl_user, False, False, 0)
        line1.pack_start(self.txt_user, True, True, 0)

        line2 = gtk.HBox(False, 5)
        line2.pack_start(self.lbl_passwd, False, False, 0)
        line2.pack_start(self.txt_passwd, True, True, 0)
        line2.pack_start(self.btn_auth, False, False, 0)

        line3 = gtk.HBox(False, 5)
        line3.pack_start(lbl_api, False, False, 0)
        line3.pack_start(self.cmb_api, True, True, 0)

        # Join HBoxes
        vbox = gtk.VBox(False, 10)
        vbox.pack_start(line3, False, False, 0)
        vbox.pack_start(line1, False, False, 0)
        vbox.pack_start(line2, False, False, 0)
        vbox.pack_start(alignment, False, False, 0)

        self.add(vbox)
        self.show_all()
        self.btn_auth.hide()

    def _refresh(self, widget):
        self.txt_user.set_text("")
        self.txt_passwd.set_text("")

        apiiter = self.cmb_api.get_active_iter()
        api = self.model_api.get(apiiter, 0)[0]
        if utils.available_libs[api][2] == utils.LOGIN_OAUTH:
            self.lbl_user.set_text("Name")
            self.lbl_passwd.set_text("PIN")
            self.txt_passwd.set_visibility(True)
            self.btn_auth.show()
        else:
            self.lbl_user.set_text("Username")
            self.lbl_passwd.set_text("Password")
            self.txt_passwd.set_visibility(False)
            self.btn_auth.hide()

    def do_auth(self, widget):
        apiiter = self.cmb_api.get_active_iter()
        api = self.model_api.get(apiiter, 0)[0]
        url = utils.available_libs[api][4]

        webbrowser.open(url, 2, True)

    def do_close(self, widget):
        self.destroy()


class ShowSearch(gtk.Window):
    def __init__(self, engine):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.engine = engine

        fullbox = gtk.HPaned()

        self.set_position(gtk.WIN_POS_CENTER)
        self.set_title('Search')
        self.set_border_width(10)

        vbox = gtk.VBox(False, 10)

        searchbar = gtk.HBox(False, 5)
        searchbar.pack_start(gtk.Label('Search'), False, False, 0)
        self.searchtext = gtk.Entry(100)
        self.searchtext.connect("activate", self.do_search)
        searchbar.pack_start(self.searchtext, True, True, 0)
        self.search_button = gtk.Button('Search')
        self.search_button.connect("clicked", self.do_search)
        searchbar.pack_start(self.search_button, False, False, 0)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.set_size_request(450, 350)

        alignment = gtk.Alignment(xalign=1.0)
        bottombar = gtk.HBox(False, 5)
        gtk.stock_add([(gtk.STOCK_APPLY, "Add", 0, 0, "")])
        self.add_button = gtk.Button(stock=gtk.STOCK_APPLY)
        self.add_button.connect("clicked", self.do_add)
        self.add_button.set_sensitive(False)
        close_button = gtk.Button(stock=gtk.STOCK_CLOSE)
        close_button.connect("clicked", self.do_close)
        bottombar.pack_start(self.add_button, False, False, 0)
        bottombar.pack_start(close_button, False, False, 0)
        alignment.add(bottombar)

        self.showlist = ShowSearchView()
        self.showlist.get_selection().connect("changed", self.select_show)

        sw.add(self.showlist)

        self.info = InfoWidget(engine)
        self.info.set_size(400, 350)

        vbox.pack_start(searchbar, False, False, 0)
        vbox.pack_start(sw, True, True, 0)
        vbox.pack_start(alignment, False, False, 0)
        fullbox.pack1(vbox)
        fullbox.pack2(self.info)
        self.add(fullbox)

    def do_add(self, widget, path=None, view_column=None):
        # Get show dictionary
        show = None
        for item in self.entries:
            if item['id'] == self.selected_show:
                show = item
                break

        if show is not None:
            try:
                self.engine.add_show(show)
                #self.do_close()
            except utils.TrackmaError, e:
                self.error_push(e.message)

    def do_search(self, widget):
        threading.Thread(target=self.task_search).start()

    def do_close(self, widget=None):
        self.destroy()

    def select_show(self, widget):
        # Get selected show ID
        (tree_model, tree_iter) = widget.get_selected()
        if not tree_iter:
            self.allow_buttons_push(False, lists_too=False)
            return

        self.selected_show = int(tree_model.get(tree_iter, 0)[0])
        self.info.load(self.showdict[self.selected_show])
        self.add_button.set_sensitive(True)

    def task_search(self):
        self.allow_buttons(False)

        try:
            self.entries = self.engine.search(self.searchtext.get_text())
        except utils.TrackmaError, e:
            self.entries = []
            self.error(e.message)

        self.showdict = dict()

        gtk.threads_enter()
        self.showlist.append_start()
        for show in self.entries:
            self.showdict[show['id']] = show
            self.showlist.append(show)
        self.showlist.append_finish()
        gtk.threads_leave()

        self.allow_buttons(True)
        self.add_button.set_sensitive(False)

    def allow_buttons_push(self, boolean):
        self.search_button.set_sensitive(boolean)

    def allow_buttons(self, boolean):
        # Thread safe
        gobject.idle_add(self.allow_buttons_push, boolean)

    def error(self, msg):
        # Thread safe
        gobject.idle_add(self.error_push, msg)

    def error_push(self, msg):
        dialog = gtk.MessageDialog(self, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, msg)
        dialog.show_all()
        dialog.connect("response", self.modal_close)

    def modal_close(self, widget, response_id):
        widget.destroy()


class ShowSearchView(gtk.TreeView):
    def __init__(self):
        gtk.TreeView.__init__(self)

        self.cols = dict()
        i = 0
        for name in ('Title', 'Type', 'Total'):
            self.cols[name] = gtk.TreeViewColumn(name)
            self.cols[name].set_sort_column_id(i)
            self.append_column(self.cols[name])
            i += 1

        #renderer_id = gtk.CellRendererText()
        #self.cols['ID'].pack_start(renderer_id, False)
        #self.cols['ID'].add_attribute(renderer_id, 'text', 0)

        renderer_title = gtk.CellRendererText()
        self.cols['Title'].pack_start(renderer_title, False)
        self.cols['Title'].set_resizable(True)
        #self.cols['Title'].set_expand(True)
        self.cols['Title'].add_attribute(renderer_title, 'text', 1)
        self.cols['Title'].add_attribute(renderer_title, 'foreground', 4)

        renderer_type = gtk.CellRendererText()
        self.cols['Type'].pack_start(renderer_type, False)
        self.cols['Type'].add_attribute(renderer_type, 'text', 2)

        renderer_total = gtk.CellRendererText()
        self.cols['Total'].pack_start(renderer_total, False)
        self.cols['Total'].add_attribute(renderer_total, 'text', 3)

        self.store = gtk.ListStore(str, str, str, str, str)
        self.set_model(self.store)

    def append_start(self):
        self.freeze_child_notify()
        self.store.clear()

    def append(self, show):
        if show['status'] == 1:
            color = '#0099cc'
        elif show['status'] == 3:
            color = '#999900'
        else:
            color = None

        row = [show['id'], show['title'], show['type'], show['total'], color]
        self.store.append(row)

    def append_finish(self):
        self.thaw_child_notify()
        self.store.set_sort_column_id(1, gtk.SORT_ASCENDING)

class ProgressCellRenderer(gtk.GenericCellRenderer):
    value = 0
    subvalue = 0
    total = 0
    eps = []
    _subheight = 5

    __gproperties__ = {
        "value": (gobject.TYPE_INT, "Value",
        "Progress percentage", 0, 1000, 0,
        gobject.PARAM_READWRITE),

        "subvalue": (gobject.TYPE_INT, "Subvalue",
        "Sub percentage", 0, 1000, 0,
        gobject.PARAM_READWRITE),

        "total": (gobject.TYPE_INT, "Total",
        "Total percentage", 0, 1000, 0,
        gobject.PARAM_READWRITE),

        "eps": (gobject.TYPE_PYOBJECT, "Episodes",
        "Available episodes", gobject.PARAM_READWRITE),
    }

    def __init__(self):
        self.__gobject_init__()
        self.value = self.get_property("value")
        self.subvalue = self.get_property("subvalue")
        self.total = self.get_property("total")
        self.eps = self.get_property("eps")

    def do_set_property(self, pspec, value):
        setattr(self, pspec.name, value)

    def do_get_property(self, pspec):
        return getattr(self, pspec.name)

    def on_render(self, window, widget, background_area, cell_area, expose_area, flags):
        cr = window.cairo_create()
        (x, y, w, h) = self.on_get_size(widget, cell_area)

        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.rectangle(x, y, w, h)
        cr.fill()

        if not self.total:
            return

        if self.subvalue:
            if self.subvalue > self.total:
                mid = w
            else:
                mid = int(w / float(self.total) * self.subvalue)

            cr.set_source_rgb(0.7, 0.7, 0.7)
            cr.rectangle(x, y+h-self._subheight, mid, h-(h-self._subheight))
            cr.fill()

        if self.value:
            if self.value >= self.total:
                cr.set_source_rgb(0.6, 0.8, 0.7)
                cr.rectangle(x, y, w, h)
            else:
                mid = int(w / float(self.total) * self.value)
                cr.set_source_rgb(0.6, 0.7, 0.8)
                cr.rectangle(x, y, mid, h)
            cr.fill()

        if self.eps:
            cr.set_source_rgb(0.4, 0.5, 0.6)
            for episode in self.eps:
                if episode > 0 and episode <= self.total:
                    start = int(w / float(self.total) * (episode - 1))
                    finish = int(w / float(self.total) * episode)
                    cr.rectangle(x+start, y+h-self._subheight, finish-start, h-(h-self._subheight))
                    cr.fill()

    def on_get_size(self, widget, cell_area):
        if cell_area == None:
            return (0, 0, 0, 0)
        x = cell_area.x
        y = cell_area.y
        w = cell_area.width
        h = cell_area.height
        return (x, y, w, h)

def main():
    app = Trackma_gtk()
    try:
        gtk.gdk.threads_enter()
        app.main()
    except utils.TrackmaFatal, e:
        md = gtk.MessageDialog(None,
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR,
            gtk.BUTTONS_CLOSE, e.message)
        md.run()
        md.destroy()
    finally:
        gtk.gdk.threads_leave()

