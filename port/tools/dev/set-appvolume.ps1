param(
    [Parameter(Mandatory = $true)][int]$ProcessId,  # process whose audio session to change
    [double]$Level = 0.15,                          # 0..1, the app's slider in the Windows volume mixer
    [int]$WaitSeconds = 60                          # wait this long for the process to open its audio
)
# Sets one process's volume in the Windows mixer (its audio session), without touching the app's
# own settings. Used by pcsx2-boot.ps1 / pcsx2-record.ps1 (quiet test runs, 15%) and socom-run.ps1
# (normal level). Plain Windows Core Audio COM calls; no other script or module needed.
Add-Type -Language CSharp @'
using System;
using System.Runtime.InteropServices;
namespace SocomAudio {
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator { }
  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator { int NotImpl1(); int GetDefaultAudioEndpoint(int flow, int role, out IMMDevice dev); }
  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice { int Activate(ref Guid iid, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o); }
  [Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionManager2 { int NotImpl1(); int NotImpl2(); int GetSessionEnumerator(out IAudioSessionEnumerator e); }
  [Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionEnumerator { int GetCount(out int n); int GetSession(int i, out IAudioSessionControl2 s); }
  [Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionControl2 {
    int NotImpl0(); int NotImpl1(); int NotImpl2(); int NotImpl3(); int NotImpl4(); int NotImpl5(); int NotImpl6(); int NotImpl7(); int NotImpl8();
    int GetSessionIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string s);
    int GetSessionInstanceIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string s);
    int GetProcessId(out uint pid);
  }
  [Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface ISimpleAudioVolume { int SetMasterVolume(float level, ref Guid ctx); int GetMasterVolume(out float level); int SetMute(bool mute, ref Guid ctx); }
  public static class Mixer {
    public static int Set(uint pid, float level) {
      var en = (IMMDeviceEnumerator)new MMDeviceEnumerator();
      IMMDevice dev; en.GetDefaultAudioEndpoint(0, 1, out dev);
      Guid iid = typeof(IAudioSessionManager2).GUID; object o;
      dev.Activate(ref iid, 23, IntPtr.Zero, out o);
      IAudioSessionEnumerator se; ((IAudioSessionManager2)o).GetSessionEnumerator(out se);
      int n; se.GetCount(out n); int hits = 0; Guid ctx = Guid.Empty;
      for (int i = 0; i < n; i++) {
        IAudioSessionControl2 s; se.GetSession(i, out s); uint p; s.GetProcessId(out p);
        if (p == pid) { ((ISimpleAudioVolume)s).SetMasterVolume(level, ref ctx); hits++; }
      }
      return hits;
    }
  }
}
'@
$deadline = (Get-Date).AddSeconds($WaitSeconds)
do {
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { exit 0 }
    $hits = 0
    try { $hits = [SocomAudio.Mixer]::Set([uint32]$ProcessId, [single]$Level) } catch { }
    if ($hits -gt 0) { exit 0 }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)
exit 1
