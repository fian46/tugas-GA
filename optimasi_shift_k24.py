import random
import numpy as np
from deap import base, creator, tools

# ==========================================
# 1. PARAMETER OPERASIONAL K-24
# ==========================================
NUM_STAFF = 6        # Fleksibel: dapat diatur 5, 6, 7, atau 8 staf
DAYS = 7             # 7 hari (Senin - Minggu)
GENOME_LENGTH = NUM_STAFF * DAYS

# Kuota minimal harian: Pagi 1, MD 1, Siang 1, Malam WAJIB SELALU 2
MIN_DEMAND = {
    'pagi': 1,
    'md': 1,
    'siang': 1,
    'malam': 2
}

# Label nama hari dan shift
DAYS_HEADER = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
DAYS_NAME = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
SHIFT_LABELS = {
    0: 'Off ',
    1: 'Pagi',
    2: 'MD  ',
    3: 'Sian',
    4: 'Mlm ',
    5: 'PgMD',  # Lembur Pagi -> MD (memenuhi kuota Pagi & MD)
    6: 'PgSi'   # Lembur Pagi -> Siang (memenuhi kuota Pagi & Siang)
}

# Parameter Algoritma Genetika
POP_SIZE = 300
GENERATIONS = 350
CX_PROB = 0.85
MUT_PROB = 0.35
INDPB = 0.05

# ==========================================
# 2. DEFINISI FITNESS & EVALUASI
# ==========================================
if not hasattr(creator, "FitnessMin"):
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
if not hasattr(creator, "Individual"):
    creator.create("Individual", list, fitness=creator.FitnessMin)

def evaluate_schedule(individual, return_details=False):
    sched = np.array(individual).reshape((NUM_STAFF, DAYS))
    penalties = 0
    logs = {
        'kuota_malam': [],
        'kuota_lain': [],
        'kerja_nonstop': [],
        'lembur': [],
        'lembur_beruntun': [],
        'transisi': [],
        'malam_beruntun': [],
        'libur_lebih': []
    }

    # ----------------------------------------------------
    # 1. HARD CONSTRAINT: Kuota Minimal Tiap Shift Harian
    # ----------------------------------------------------
    for d in range(DAYS):
        day_shifts = sched[:, d]

        p_count = np.count_nonzero((day_shifts == 1) | (day_shifts == 5) | (day_shifts == 6))
        m_count = np.count_nonzero((day_shifts == 2) | (day_shifts == 5))
        s_count = np.count_nonzero((day_shifts == 3) | (day_shifts == 6))
        n_count = np.count_nonzero(day_shifts == 4)

        # Shift malam WAJIB SELALU 2 orang (Hard Constraint Tertinggi)
        if n_count < MIN_DEMAND['malam']:
            kekurangan = MIN_DEMAND['malam'] - n_count
            penalties += kekurangan * 4000
            logs['kuota_malam'].append(f"{DAYS_NAME[d]}: Shift Malam kurang {kekurangan} orang (+{kekurangan * 4000})")

        # Shift Pagi, MD, Siang minimal 1 orang
        if p_count < MIN_DEMAND['pagi']:
            kekurangan = MIN_DEMAND['pagi'] - p_count
            penalties += kekurangan * 1500
            logs['kuota_lain'].append(f"{DAYS_NAME[d]}: Shift Pagi kurang {kekurangan} orang (+{kekurangan * 1500})")
        if m_count < MIN_DEMAND['md']:
            kekurangan = MIN_DEMAND['md'] - m_count
            penalties += kekurangan * 1500
            logs['kuota_lain'].append(f"{DAYS_NAME[d]}: Shift MD kurang {kekurangan} orang (+{kekurangan * 1500})")
        if s_count < MIN_DEMAND['siang']:
            kekurangan = MIN_DEMAND['siang'] - s_count
            penalties += kekurangan * 1500
            logs['kuota_lain'].append(f"{DAYS_NAME[d]}: Shift Siang kurang {kekurangan} orang (+{kekurangan * 1500})")

    # ----------------------------------------------------
    # 2. ATURAN TRANSISI, BEBAN KERJA, & LEMBUR
    # ----------------------------------------------------
    for s in range(NUM_STAFF):
        staff_shifts = sched[s, :]

        # 2a. DILARANG BEKERJA > 6 HARI (Wajib Libur Minimal 1 Hari Seminggu)
        # Hard Constraint Mutlak: Penalti 4000 jika kerja 7 hari nonstop
        days_off = np.count_nonzero(staff_shifts == 0)
        if days_off < 1:
            penalties += 4000
            logs['kerja_nonstop'].append(f"Karyawan {s+1}: Bekerja 7 hari tanpa libur (DILARANG KERJA > 6 HARI) (+4000)")
        elif days_off > 3:
            kelebihan = days_off - 3
            penalties += kelebihan * 50
            logs['libur_lebih'].append(f"Karyawan {s+1}: Terlalu banyak libur ({days_off} hari) (+{kelebihan * 50})")

        # 2b. Penalti biaya penggunaan lembur (Rp / beban lembur)
        for d in range(DAYS):
            shift_val = staff_shifts[d]
            if shift_val == 5:
                penalties += 15
                logs['lembur'].append(f"Karyawan {s+1} ({DAYS_NAME[d]}): Ambil lembur PgMD (+15)")
            elif shift_val == 6:
                penalties += 15
                logs['lembur'].append(f"Karyawan {s+1} ({DAYS_NAME[d]}): Ambil lembur PgSi (+15)")

        # 2c. Transisi antar-hari
        for d in range(DAYS - 1):
            curr, nxt = staff_shifts[d], staff_shifts[d + 1]

            # Pasca-Shift Malam (4): Dilarang langsung masuk pagi/MD
            if curr == 4:
                if nxt in [1, 5, 6]:
                    penalties += 2500
                    logs['transisi'].append(f"Karyawan {s+1} ({DAYS_NAME[d]} -> {DAYS_NAME[d+1]}): Tabrakan fisik Malam -> {SHIFT_LABELS[nxt].strip()} (+2500)")
                elif nxt == 2:
                    penalties += 2000
                    logs['transisi'].append(f"Karyawan {s+1} ({DAYS_NAME[d]} -> {DAYS_NAME[d+1]}): Jeda tidak manusiawi Malam -> MD (+2000)")

            # Mencegah lembur 2 hari berturut-turut
            if curr in [5, 6] and nxt in [5, 6]:
                penalties += 80
                logs['lembur_beruntun'].append(f"Karyawan {s+1} ({DAYS_NAME[d]} -> {DAYS_NAME[d+1]}): Lembur beruntun {SHIFT_LABELS[curr].strip()} -> {SHIFT_LABELS[nxt].strip()} (+80)")

        # 2d. Batas shift malam beruntun (maksimal 2 malam berturut-turut)
        night_streak = 0
        for d in range(DAYS):
            if staff_shifts[d] == 4:
                night_streak += 1
                if night_streak > 2:
                    penalties += 250
                    logs['malam_beruntun'].append(f"Karyawan {s+1} ({DAYS_NAME[d]}): Shift malam ke-{night_streak} berturut-turut (+250)")
            else:
                night_streak = 0

    if return_details:
        return penalties, logs
    return (penalties,)

# ==========================================
# 3. REGISTRASI OPERATOR DEAP
# ==========================================
toolbox = base.Toolbox()

toolbox.register("attr_shift", random.randint, 0, 6)
toolbox.register("individual", tools.initRepeat, creator.Individual, toolbox.attr_shift, n=GENOME_LENGTH)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)

toolbox.register("evaluate", evaluate_schedule)
toolbox.register("mate", tools.cxTwoPoint)
toolbox.register("mutate", tools.mutUniformInt, low=0, up=6, indpb=INDPB)
toolbox.register("select", tools.selTournament, tournsize=4)

# ==========================================
# 4. LOOP ITERATIF
# ==========================================
def main():
    population = toolbox.population(n=POP_SIZE)
    hof = tools.HallOfFame(1)

    for ind in population:
        ind.fitness.values = toolbox.evaluate(ind)
    hof.update(population)

    print("=" * 62)
    print(f"{'Gen':<6} | {'Penalti Terbaik':<20} | {'Penalti Rata-rata':<20}")
    print("=" * 62)

    for gen in range(1, GENERATIONS + 1):
        offspring = toolbox.select(population, len(population) - 1)
        offspring = list(map(toolbox.clone, offspring))

        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < CX_PROB:
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values

        for mutant in offspring:
            if random.random() < MUT_PROB:
                toolbox.mutate(mutant)
                del mutant.fitness.values

        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        for ind in invalid_ind:
            ind.fitness.values = toolbox.evaluate(ind)

        # Elitism
        offspring.append(toolbox.clone(hof[0]))
        population[:] = offspring
        hof.update(population)

        penalties = [ind.fitness.values[0] for ind in population]
        best_pen = min(penalties)
        avg_pen = np.mean(penalties)

        if gen % 10 == 0 or best_pen <= 150:
            print(f"{gen:<6} | {int(best_pen):<20} | {avg_pen:<20.1f}")

        # Kondisi berhenti awal jika solusi optimal (semua hard constraints lolos)
        if best_pen <= 150:
            print("-" * 62)
            print(f"[!] Jadwal optimal tanpa pelanggaran ditemukan pada Generasi ke-{gen}!")
            break

    # ==========================================
    # 5. CETAK MATRIKS JADWAL AKHIR
    # ==========================================
    best_ind = hof[0]
    final_pen, logs = evaluate_schedule(best_ind, return_details=True)
    schedule = np.array(best_ind).reshape((NUM_STAFF, DAYS))

    print("\n" + "=" * 70)
    print(f"JADWAL KERJA K-24 ({NUM_STAFF} Staf | Total Penalti: {final_pen})")
    print("=" * 70)
    print(f"{'Staf':<10} " + " ".join([f"{d:^5}" for d in DAYS_HEADER]) + " | Total Hari Kerja")
    print("-" * 70)

    for s in range(NUM_STAFF):
        row = [SHIFT_LABELS[schedule[s, d]] for d in range(DAYS)]
        off_count = np.count_nonzero(schedule[s, :] == 0)
        work_days = DAYS - off_count
        print(f"Karyawan {s+1:<2} " + " ".join([f"{r:^5}" for r in row]) + f" | {work_days} hari (Off: {off_count})")

    print("\nRekap Kuota Harian & Penggunaan Lembur:")
    total_lembur = 0
    all_demands_met = True
    for d in range(DAYS):
        col = schedule[:, d]
        p = np.count_nonzero((col == 1) | (col == 5) | (col == 6))
        m = np.count_nonzero((col == 2) | (col == 5))
        s = np.count_nonzero((col == 3) | (col == 6))
        n = np.count_nonzero(col == 4)
        lembur = np.count_nonzero((col == 5) | (col == 6))
        total_lembur += lembur

        if p < MIN_DEMAND['pagi'] or m < MIN_DEMAND['md'] or s < MIN_DEMAND['siang'] or n < MIN_DEMAND['malam']:
            all_demands_met = False

        status_lembur = f" (Lembur: {lembur})" if lembur > 0 else ""
        print(f"{DAYS_HEADER[d]}: Pagi={p}/{MIN_DEMAND['pagi']} | MD={m}/{MIN_DEMAND['md']} | Siang={s}/{MIN_DEMAND['siang']} | Malam={n}/{MIN_DEMAND['malam']}{status_lembur}")

    print("-" * 70)
    if all_demands_met:
        print("[v] STATUS: SEMUA KUOTA HARIAN TERPENUHI 100%! (Shift malam selalu 2 orang)")
    else:
        print("[!] STATUS: Terdapat kekurangan kuota harian pada shift tertentu.")

    # ==========================================
    # 6. RINCIAN LENGKAP PENALTI (TRANSPARANSI SKOR)
    # ==========================================
    print("\n" + "=" * 70)
    print(f"RINCIAN LENGKAP KOMPONEN PENALTI (Total Skor: {final_pen})")
    print("=" * 70)

    # A. Pelanggaran Kuota Malam
    print("1. Kuota Shift Malam (Wajib Selalu 2 Orang):")
    if logs['kuota_malam']:
        for item in logs['kuota_malam']:
            print(f"   [!] {item}")
    else:
        print("   [v] Terpenuhi 100% (Semua hari terisi 2 staf malam)")

    # B. Pelanggaran Hari Kerja > 6 Hari
    print("\n2. Batasan Hari Kerja (Maksimal 6 Hari / Wajib Libur >= 1 Hari):")
    if logs['kerja_nonstop']:
        for item in logs['kerja_nonstop']:
            print(f"   [!] {item}")
    else:
        print("   [v] Terpenuhi 100% (Tidak ada karyawan bekerja > 6 hari)")

    # C. Kuota Lain
    print("\n3. Kuota Shift Lain (Pagi, MD, Siang):")
    if logs['kuota_lain']:
        for item in logs['kuota_lain']:
            print(f"   [!] {item}")
    else:
        print("   [v] Terpenuhi 100% (Pagi, MD, Siang terpenuhi setiap hari)")

    # D. Lembur
    sub_lembur = len(logs['lembur']) * 15
    print(f"\n4. Penggunaan Shift Lembur (Subtotal: +{sub_lembur}):")
    if logs['lembur']:
        for item in logs['lembur']:
            print(f"   - {item}")
    else:
        print("   (Tidak ada shift lembur)")

    # E. Lembur Beruntun
    sub_lembur_beruntun = len(logs['lembur_beruntun']) * 80
    print(f"\n5. Lembur Berturut-turut (Subtotal: +{sub_lembur_beruntun}):")
    if logs['lembur_beruntun']:
        for item in logs['lembur_beruntun']:
            print(f"   - {item}")
    else:
        print("   (Tidak ada lembur berturut-turut)")

    # F. Transisi
    print(f"\n6. Pelanggaran Transisi Terlarang Pasca-Malam:")
    if logs['transisi']:
        for item in logs['transisi']:
            print(f"   - {item}")
    else:
        print("   (Tidak ada pelanggaran transisi)")

    # G. Malam Beruntun
    sub_malam = len(logs['malam_beruntun']) * 250
    print(f"\n7. Shift Malam Berturut-turut > 2 Malam (Subtotal: +{sub_malam}):")
    if logs['malam_beruntun']:
        for item in logs['malam_beruntun']:
            print(f"   - {item}")
    else:
        print("   (Tidak ada staf dinas malam > 2 malam berturut-turut)")

    # H. Libur Lebih
    if logs['libur_lebih']:
        print(f"\n8. Kelebihan Hari Libur (> 3 Hari):")
        for item in logs['libur_lebih']:
            print(f"   - {item}")

    print("=" * 70)

if __name__ == "__main__":
    main()
