import sys
from types import ModuleType

# Compatibility for Python 3.13+ (audioop was removed)
try:
    import audioop
except ImportError:
    try:
        import audioop_lts as audioop
        import sys
        sys.modules["audioop"] = audioop
    except ImportError:
        pass # Will fail later with clear error if used

import os
import asyncio
import numpy as np
import sounddevice as sd
# from shazamio import Shazam
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

class Recorder:
    def __init__(self, samplerate=44100):
        self.samplerate = samplerate
        self.recording = False
        self.paused = False
        self.audio_data = []
        self.stream = None
        self.current_level = 0.0

    def get_devices(self):
        return sd.query_devices()

    def _callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        
        # Calculate peak level for UI (always monitor if stream is active)
        self.current_level = float(np.max(np.abs(indata)))
        
        if self.recording and not self.paused:
            self.audio_data.append(indata.copy())

    def start(self, device_index):
        if self.stream is None:
            self.audio_data = []
            self.stream = sd.InputStream(
                device=device_index,
                channels=2,
                samplerate=self.samplerate,
                callback=self._callback
            )
            self.stream.start()
        self.recording = True
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.recording = False
        self.paused = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        if not self.audio_data:
            return None
            
        full_data = np.concatenate(self.audio_data, axis=0)
        int_data = (full_data * 32767).astype(np.int16)
        return AudioSegment(
            int_data.tobytes(),
            frame_rate=self.samplerate,
            sample_width=2,
            channels=2
        )

    def get_level(self):
        return self.current_level

import subprocess

class TapeProcessor:
    def __init__(self, ffmpeg_bin):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffplay_path = os.path.join(ffmpeg_bin, "ffplay.exe")
        AudioSegment.converter = os.path.join(ffmpeg_bin, "ffmpeg.exe")
        AudioSegment.ffprobe = os.path.join(ffmpeg_bin, "ffprobe.exe")
        self.shazam = None
        self.audio = None
        self.tracks = []
        self._play_process = None

    def load_audio(self, audio_path):
        self.audio = AudioSegment.from_file(audio_path)
        return self.audio

    def set_audio(self, audio_segment):
        self.audio = audio_segment

    def play_track(self, index):
        self.play_segment(index)

    def play_track_start(self, index, duration_ms=5000):
        self.play_segment(index, segment_type="start", duration_ms=duration_ms)

    def play_track_end(self, index, duration_ms=5000):
        self.play_segment(index, segment_type="end", duration_ms=duration_ms)

    def play_segment(self, index, segment_type="full", duration_ms=30000):
        try:
            if index < 0 or index >= len(self.tracks): return
            self.stop_playback()
            
            track = self.tracks[index]
            full_segment = self.audio[track['start'] : track['end']]
            
            if segment_type == "start":
                segment = full_segment[:duration_ms]
            elif segment_type == "end":
                segment = full_segment[-duration_ms:]
            else:
                segment = full_segment[:duration_ms] if len(full_segment) > duration_ms else full_segment

            temp_preview = f"preview_seg_{index}_{segment_type}.mp3"
            segment.export(temp_preview, format="mp3")
            preview_path = os.path.abspath(temp_preview)

            if preview_path:
                self._play_process = subprocess.Popen(
                    [self.ffplay_path, "-nodisp", "-autoexit", preview_path],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
        except Exception as e:
            print(f"Playback error: {e}")

    def stop_playback(self):
        try:
            if self._play_process:
                self._play_process.terminate()
                self._play_process = None
        except Exception as e:
            print(f"Stop playback error: {e}")

    def get_track_preview(self, index, duration_ms=30000):
        if index < 0 or index >= len(self.tracks): return None
        track = self.tracks[index]
        segment = self.audio[track['start'] : track['end']]
        
        if len(segment) > duration_ms:
            segment = segment[:duration_ms]
            
        temp_preview = f"preview_{index}.mp3"
        segment.export(temp_preview, format="mp3")
        return os.path.abspath(temp_preview)

    async def detect_tracks(self, silence_thresh, min_silence_len=1000):
        if not self.audio: return []
        chunks = detect_nonsilent(
            self.audio, 
            min_silence_len=min_silence_len, 
            silence_thresh=silence_thresh
        )
        self.tracks = []
        for start, end in chunks:
            self.tracks.append({
                'start': start,
                'end': end,
                'artist': 'Unknown Artist',
                'title': 'Unknown Title',
                'album': '',
                'year': '',
                'genre': '',
                'cover_url': '',
                'status': 'Pending'
            })
        return self.tracks

    async def identify_track(self, index):
        if index < 0 or index >= len(self.tracks): return
        track = self.tracks[index]
        
        if self.shazam is None:
            try:
                from shazamio import Shazam
                self.shazam = Shazam()
            except Exception as e:
                print(f"Failed to load Shazam: {e}")
                track['status'] = 'Error (No Shazam)'
                return track

        segment = self.audio[track['start'] : track['end']]
        
        duration = len(segment)
        points = [duration // 2, duration // 4, (3 * duration) // 4, duration // 5]
        
        for p in points:
            sample_start = p
            sample_end = min(p + 10000, duration)
            sample = segment[sample_start:sample_end]
            if len(sample) < 3000: continue
            
            temp_path = f"temp_id_{index}_{p}.mp3"
            sample.export(temp_path, format="mp3")
            
            try:
                out = await self.shazam.recognize(temp_path)
                if out and 'track' in out:
                    track_data = out['track']
                    track['artist'] = track_data.get('subtitle', 'Unknown Artist')
                    track['title'] = track_data.get('title', 'Unknown Title')
                    
                    # Extra metadata
                    track['album'] = track_data.get('sections', [{}])[0].get('metadata', [{}])[0].get('text', '') # Often album is first metadata
                    track['genre'] = track_data.get('genres', {}).get('primary', '')
                    
                    # Try to find year in metadata
                    metadata = track_data.get('sections', [{}])[0].get('metadata', [])
                    for item in metadata:
                        if item.get('title') == 'Released':
                            track['year'] = item.get('text', '')
                    
                    # Images
                    images = track_data.get('images', {})
                    track['cover_url'] = images.get('coverarthq') or images.get('coverart', '')
                    
                    track['status'] = 'Identified'
                    return track
            except Exception as e:
                print(f"Identification attempt error: {e}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        
        track['status'] = 'Failed'
        return track

    def export_single_track(self, root_dir, album_name, track_num, track, file_format="mp3"):
        dest_dir = os.path.join(root_dir, album_name)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        segment = self.audio[track['start'] : track['end']]
        
        # Base tags
        tags = {
            'artist': track.get('artist', 'Unknown Artist'),
            'title': track.get('title', 'Unknown Title'),
            'album': track.get('album') or album_name,
            'tracknumber': str(track_num),
            'date': track.get('year', ''),
            'genre': track.get('genre', '')
        }

        safe_title = "".join([c for c in track['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
        safe_artist = "".join([c for c in track['artist'] if c.isalnum() or c in (' ', '-', '_')]).strip()
        if not safe_title: safe_title = "Unknown"
        if not safe_artist: safe_artist = "Unknown"

        filename = f"{track_num:02d} - {safe_artist} - {safe_title}.{file_format}"
        dest_path = os.path.join(dest_dir, filename)

        if file_format == "wav":
            segment.export(dest_path, format="wav")
        else:
            segment.export(dest_path, format=file_format, tags=tags)
            
            # Embed cover art if available and using mutagen
            cover_url = track.get('cover_url')
            if cover_url and file_format == "mp3":
                try:
                    import httpx
                    from mutagen.id3 import ID3, APIC
                    from mutagen.mp3 import MP3
                    
                    response = httpx.get(cover_url)
                    if response.status_code == 200:
                        audio = MP3(dest_path, ID3=ID3)
                        try:
                            audio.add_tags()
                        except: pass
                        
                        audio.tags.add(APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3,
                            desc=u'Cover',
                            data=response.content
                        ))
                        audio.save()
                except Exception as e:
                    print(f"Error embedding cover art: {e}")

        return dest_path

    def export_organized(self, root_dir, band_id, side, file_format="mp3", progress_callback=None):
        if not self.audio:
            raise ValueError("No audio data to export.")
        if not self.tracks:
            raise ValueError("No tracks detected. Run Split & ID first.")

        album_name = f"Band {band_id}-{side}"
        total = len(self.tracks)
        for i, track in enumerate(self.tracks):
            if progress_callback:
                progress_callback(i, total, f"Exporting track {i+1}/{total}")
            self.export_single_track(root_dir, album_name, i+1, track, file_format)

        if progress_callback:
            progress_callback(total, total, "Export completed!")

