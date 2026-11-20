import Gio from 'gi://Gio';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const OBJECT_PATH = '/org/gnome/Shell/Extensions/XiaomiRemoteFocus';
const IFACE = `
<node>
  <interface name="org.xiaomi.RemoteFocus">
    <method name="GetFocus">
      <arg name="appId" type="s" direction="out"/>
      <arg name="wmClass" type="s" direction="out"/>
      <arg name="title" type="s" direction="out"/>
    </method>
  </interface>
</node>`;

export default class XiaomiRemoteFocus extends Extension {
    enable() {
        // A tiny read-only bridge. No key interception, no timers, no shell
        // monkey-patching, and no remote/network interfaces.
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, OBJECT_PATH);
    }

    GetFocus() {
        const window = global.display.focus_window;
        if (!window)
            return ['', '', ''];
        const app = Shell.WindowTracker.get_default().get_window_app(window);
        return [
            app?.get_id?.() ?? '',
            window.get_wm_class?.() ?? '',
            window.get_title?.() ?? '',
        ];
    }

    disable() {
        this._dbus?.unexport();
        this._dbus = null;
    }
}
