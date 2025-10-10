import os
from typing import List, Tuple, Dict
from rapidfuzz import fuzz, process


class AudioManager:
    def __init__(self, audio_dir: str):
        self.audio_dir = audio_dir
        self.audio_files = {}  # Changed to dict: {relative_path: display_name}
        self._load_audio_files()
    
    def _load_audio_files(self) -> None:
        """Load all audio files (.ogg) from the audio directory and subdirectories"""
        if not os.path.exists(self.audio_dir):
            os.makedirs(self.audio_dir)
            return
        
        # Walk through all subdirectories
        for root, _, files in os.walk(self.audio_dir):
            for file in files:
                if file.endswith(('.wav', '.ogg')):  # Support both formats
                    # Get full path
                    full_path = os.path.join(root, file)
                    
                    # Get relative path from audio_dir
                    relative_path = os.path.relpath(full_path, self.audio_dir)
                    
                    # Create display name with category
                    # Example: protoss/zealot/attack.wav -> [Protoss/Zealot] attack
                    path_parts = relative_path.replace('\\', '/').split('/')
                    
                    if len(path_parts) > 1:
                        # Has subdirectories
                        category = '/'.join(path_parts[:-1])
                        filename = path_parts[-1]
                        # Remove extension (.ogg)
                        filename = filename.rsplit('.', 1)[0]
                        display_name = f"[{category.title()}] {filename}"
                    else:
                        # File in root audio_files directory
                        display_name = file.rsplit('.', 1)[0]
                    
                    self.audio_files[relative_path] = display_name
    
    def search(self, query: str, limit: int = 50) -> List[Tuple[str, str, float]]:
        """
        Search for audio files matching the query
        Returns list of (relative_path, display_name, score) tuples
        """
        if not query:
            return []
        
        # Search in display names
        display_names = list(self.audio_files.values())
        relative_paths = list(self.audio_files.keys())
        
        # Use fuzzy matching with partial ratio for better results
        results = process.extract(
            query, 
            display_names, 
            scorer=fuzz.partial_ratio,
            limit=limit
        )
        
        # Match display names back to relative paths and filter by score
        matched_results = []
        for display_name, score, _ in results:
            if score > 30:  # Minimum score threshold
                # Find the relative path for this display name
                for rel_path, disp_name in self.audio_files.items():
                    if disp_name == display_name:
                        matched_results.append((rel_path, display_name, score))
                        break
        
        return matched_results
    
    def get_file_path(self, relative_path: str) -> str:
        """Get full path to audio file from relative path"""
        return os.path.join(self.audio_dir, relative_path)
    
    def get_all_files(self) -> Dict[str, str]:
        """Get all audio files as {relative_path: display_name}"""
        return self.audio_files.copy()
    
    def get_stats_by_category(self) -> Dict[str, int]:
        """Get count of files per main category (protoss/terran/zerg/music)"""
        stats = {}
        for relative_path in self.audio_files.keys():
            category = relative_path.split(os.sep)[0]
            stats[category] = stats.get(category, 0) + 1
        return stats
