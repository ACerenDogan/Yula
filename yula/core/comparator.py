from typing import Dict, List

def compare_with_baseline(current_scan: Dict[str, dict], saved_baseline: Dict[str, str]) -> Dict[str, List[dict]]:
    """
    Şu anki tarama sonuçları ile veritabanındaki kayıtlı baseline hash'lerini
    karşılaştırarak değişiklikleri (NEW, MODIFIED, DELETED, UNCHANGED) sınıflandırır.
    """
    results = {
        "MODIFIED": [],
        "NEW": [],
        "DELETED": [],
        "UNCHANGED": []
    }

    current_files = set(current_scan.keys())
    baseline_files = set(saved_baseline.keys())

    # 1. Silinen Dosyaları Bul (Baseline'da var ama artık diskte yok)
    for file_path in (baseline_files - current_files):
        results["DELETED"].append({
            "path": file_path,
            "old_hash": saved_baseline[file_path]
        })

    # 2. Yeni Eklenen Dosyaları Bul (Diskte var ama Baseline'da yok)
    for file_path in (current_files - baseline_files):
        results["NEW"].append({
            "path": file_path,
            "new_hash": current_scan[file_path]["hash"]
        })

    # 3. İki tarafta da olan dosyaları karşılaştır (Değişti mi / Aynı mı?)
    for file_path in (current_files & baseline_files):
        old_hash = saved_baseline[file_path]
        new_hash = current_scan[file_path]["hash"]

        if old_hash != new_hash:
            results["MODIFIED"].append({
                "path": file_path,
                "old_hash": old_hash,
                "new_hash": new_hash
            })
        else:
            results["UNCHANGED"].append({
                "path": file_path,
                "hash": old_hash
            })

    return results