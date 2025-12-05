import os
import re
import struct
import subprocess # Para chamar o executável C
import json       # Para parsear a saída JSON
import pandas as pd
import numpy as np
import json
from PyQt6.QtCore import QObject, pyqtSignal

from src.utils.resource_paths import find_decoder_executable

signal_name_map = {
    # =======================
    # Asa Fixa (Fixed Wing)
    # =======================
    'Monit_44_S1': 'BreakVTOL',
    'Monit_9_S1' : 'Rudder',
    'Monit_9_S2' : 'Elevator',
    'Monit_10_S1': 'Engine',
    'Monit_10_S2': 'Aileron',
    'Monit_11_S1': 'Fail_Number',
    'Monit_58_S1': 'Protection_Number',
    'Monit_2_S1' : 'FW_altitude',           # rótulo visto no slide (cinza)
    'Monit_2_S2' : 'WindCorrectedCourse',
    'Monit_3_S1' : 'FinalPitchRef',
    'Monit_46_S1': 'AileronR',
    'Monit_46_S2': 'AileronL',
    'Monit_53_S19': 'Parachute',

    # =========
    # GNSS
    # =========
    'Monit_113_S1': 'Latitude_PA1',
    'Monit_114_S1': 'Longitude_PA1',
    'Monit_115_S1': 'Altitude_PA1',
    'Monit_81_S2' : 'VeIN_PA1',             # velocidade Norte? (do slide)
    'Monit_82_S1' : 'VeE_PA1',              # velocidade Leste?
    'Monit_82_S2' : 'VeU_PA1',              # velocidade Up?
    'Monit_69_S2' : 'GNSS_NoS',             # Number of Satellites
    'Monit_70_S1' : 'GNSS_LatError',
    'Monit_70_S2' : 'GNSS_LonError',
    'Monit_71_S1' : 'GNSS_AltError',
    'Monit_71_S2' : 'ASI',                  # do seu mapeamento anterior
    'Monit_124_S1': 'GNSS_Pos_isUp',

    # GNSS pacote/seleção (booleans vindos de S128)
    'Monit_128_S1': 'GNSS1_PackageFail',
    'Monit_128_S2': 'GNSS2_PackageFail',
    'Monit_128_S3': 'NavSelected',          # XGCS_NavSelector no slide
    'Monit_128_S4': 'GNSS_MSB_bundle',      # linha MSB no slide (mantemos bruto)

    'Monit_96_S1' : 'GNSS_FailNumber',
    'Monit_99_S1' : 'GNSS_Val_Quality',
    'Monit_99_S2' : 'GNSS_Val_DiffAgeSolution',
    'Monit_124_S23': 'GNSS_Health',         # do bloco GNSS Health_PA1

    # =========
    # AHRS
    # =========
    'Monit_64_S2': 'acel_x',
    'Monit_65_S1': 'acel_y',
    'Monit_65_S2': 'acel_z',

    'Monit_67_S1': 'AHRS_yaw',              # rad
    'Monit_66_S1': 'AHRS_roll',             # rad
    'Monit_66_S2': 'AHRS_pitch',            # rad
    'Monit_68_S1': 'AHRS_q',                # visto no slide (p,q,r)
    'Monit_68_S2': 'AHRS_r',

    'Monit_74_S1': 'Mag_X',                 # no slide, alguns rótulos são K-; padronizamos
    'Monit_75_S1': 'Mag_Y',
    'Monit_75_S2': 'Mag_Z',
    'Monit_83_S1': 'Declination',
    'Monit_124_S7': 'IMU_Mag_isUp',

    'Monit_61_S2': 'AHRS_pos_x_cm',
    'Monit_62_S1': 'AHRS_pos_y_cm',
    'Monit_62_S2': 'AHRS_pos_z_cm',
    'Monit_63_S1': 'AHRS_vel_x_cm',
    'Monit_63_S2': 'AHRS_vel_y_cm',
    'Monit_64_S1': 'AHRS_vel_z_cm',

    # =========
    # EKF
    # =========
    'Monit_78_S2': 'EKF_pos_x',
    'Monit_79_S1': 'EKF_pos_y',
    'Monit_72_S2': 'EKF_pos_z',

    'Monit_72_S1': 'EKF_FailSafe',
    'Monit_69_S1': 'EKF_HealthStatus',

    'Monit_73_S2': 'EKF_roll',              # deg no slide (R2D)
    'Monit_74_S1': 'EKF_pitch',
    'Monit_78_S1': 'EKF_yaw',

    'Monit_80_S1': 'EKF_vel_x',
    'Monit_80_S2': 'EKF_vel_y',
    'Monit_73_S1': 'EKF_vel_z',

    'Monit_90_S2': 'EKF_flags',

    # =========
    # VTOL
    # =========
    'Monit_13_S1': 'poscontrol_state',
    'Monit_13_S2': 'transition_stage',
    'Monit_53_S2': 'in_transition',
    'Monit_53_S3': 'hold_stabilize',
    'Monit_53_S4': 'hold_hover',
    'Monit_53_S5': 'PhaseOne_timer_finished',
    'Monit_53_S6': 'in_vtol_takeoff',
    'Monit_53_S7': 'in_vtol_land',
    'Monit_53_S8': 'assisted_flight',
    'Monit_53_S9': 'relax_auto',

    'Monit_14_S1': 'VTOL_roll_reference',
    'Monit_14_S2': 'VTOL_pitch_reference',
    'Monit_15_S1': 'VTOL_yaw_reference',

    'Monit_16_S1': 'pos_target_z',
    'Monit_16_S2': 'vel_desired_xy',
    'Monit_17_S1': 'unused_17_S1',         # reservado (aparece no quadro)

    'Monit_53_S18': 'ForceActuationEnable',
    'Monit_53_S17': 'KillSwitch',

    # =========
    # RC e Sistema
    # =========
    'Monit_1_S1' : 'SystemCounter',
    'Monit_76_S2': 'Voltage',               # Va2bVDC_PA1 no slide
    'Monit_59_S3': 'OpMode_PA1',
    'Monit_59_S2': 'Operation_Mode',
    'Monit_59_S1': 'OpMode_from_pilot',
    'Monit_18_S2': 'external_FS',
    'Monit_53_S545': 'internal_FS',         # índice incomum no slide; mantemos etiqueta
    'Monit_19_S2': 'GroundLevel',
    'Monit_15_S2': 'RPACheckSum',
    'Monit_53_S34': 'From_takeoff',
    'Monit_124_S4': 'MPDC_isUp',
    'Monit_53_S20': 'disarm_radio',
    'Monit_53_S21': 'FW_Manual',
    'Monit_124_S3': 'ADC_isUP',
    'Monit_53_S12': 'CriticalLandStage',
    'Monit_53_S10': 'ManualTransition_RPA',

    # =========
    # Read Counter
    # =========
    'Monit_84_S1': 'Mag_ReadCounter',
    'Monit_95_S2': 'EDC_ReadCounter',
    'Monit_85_S2': 'GNSS2_Pos_ReadCounter',
    'Monit_77_S1': 'GNSS2_Vel_ReadCounter',
    'Monit_86_S1': 'GNSS1_Pos_ReadCounter',
    'Monit_86_S2': 'GNSS1_Vel_ReadCounter',
    'Monit_87_S1': 'RC_ReadCounter',
    'Monit_98_S1': 'RC_ReadCounter_2',

    # =========
    # EDC / Engine / Fuel
    # =========
    'Monit_98_S2': 'RPM',                   # Rotation_PA1
    'Monit_81_S1': 'CHT',
    'Monit_76_S1': 'FuelLevel_dig',         # no slide EDC: FuelLevelAnalog/Digital; padronizamos
    'Monit_124_S8': 'FuelLevel_anag',
    'Monit_124_S5': 'EDC_isUp',

    # =========
    # Others Velocities / Pressão dinâmica -> EAS
    # =========
    'Monit_88_S1': 'ADC_DynamicPressure',

    # =========
    # DCM
    # =========
    'Monit_94_S1': 'DCM_roll',
    'Monit_94_S2': 'DCM_pitch',
    'Monit_95_S1': 'DCM_yaw',
}

# ==========================================================
# === Função para chamar o Decoder C e gerar DataFrame ===
# ==========================================================

def parse_spi_log_via_c(file_path):
    """
    Chama o decoder C externo, captura saída JSON (stdout),
    e transforma em um DataFrame Pandas unificado.
    """
    # --- Configuração ---
    decoder_path = find_decoder_executable()
    if not decoder_path or not os.path.exists(decoder_path):
        print("ERRO: Uaaai, cade o 'decoder.exe'?? DEVOLVE")
        return pd.DataFrame()

    if not os.path.exists(file_path):
        print(f"Meu querido, num tem spi.log no '{file_path}' nao!")
        return pd.DataFrame()

    # --- Execução do Subprocesso ---
    stdout_data = ""
    stderr_data = ""
    try:
        #print(f"DEBUG: Executando decoder C: {decoder_exe_path} \"{file_path}\"")
        process = subprocess.Popen(
            [str(decoder_path), file_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding='utf-8', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        stdout_data, stderr_data = process.communicate(timeout=60)
        return_code = process.returncode

        if stderr_data:
            print(f"--- Mensagens do Decoder C ({os.path.basename(file_path)}) ---"); print(stderr_data.strip()); print("-"*(len(stderr_data.strip())+4))
        if return_code != 0:
            print(f"ERRO: Decoder C falhou (código: {return_code})"); return pd.DataFrame()
        if not stdout_data:
             print("AVISO: Decoder C não produziu saída JSON."); return pd.DataFrame()

    except FileNotFoundError: print(f"ERRO: Comando '{decoder_exe_path}' não encontrado."); return pd.DataFrame()
    except subprocess.TimeoutExpired: print(f"ERRO: Decoder C timeout (>60s) em {file_path}."); process.kill(); return pd.DataFrame()
    except Exception as e: print(f"ERRO CRÍTICO ao executar decoder C: {e}"); import traceback; traceback.print_exc(); return pd.DataFrame()

    # --- Processamento da Saída JSON ---
    parsed_data = []
    lines = stdout_data.strip().split('\n')
    #print(f"DEBUG: Decoder C produziu {len(lines)} linhas JSON.")
    for i, line in enumerate(lines):
        line = line.strip();
        if not line: continue
        try:
            packet = json.loads(line)
            if 'timestamp' in packet: parsed_data.append(packet)
        except json.JSONDecodeError as e: print(f"Deu erroooo na linha {i+1}: {e}\nLinha: '{line}'"); continue
    if not parsed_data: print("AVISO: cade o timestamp? kkkkkk"); return pd.DataFrame()

    # --- Criação e Agregação do DataFrame ---
    df_raw = pd.DataFrame(parsed_data)
    
    # Converte timestamp UNIX para datetime
    df_raw['Timestamp'] = pd.to_datetime(df_raw['timestamp'], unit='s', origin='unix', errors='coerce')
    df_raw = df_raw.dropna(subset=['Timestamp']) # Remove linhas onde a conversão falhou

    if df_raw.empty: print("AVISO: Nenhum timestamp válido após conversão."); return pd.DataFrame()

    # ### CORREÇÃO: Filtra timestamps absurdos ###
    # Define um período razoável (ex: 2010 até 1 ano no futuro)
    # Ajuste conforme necessário
    min_valid_ts = pd.Timestamp('2010-01-01')
    max_valid_ts = pd.Timestamp.now() + pd.Timedelta(days=365)
    df_filtered = df_raw[(df_raw['Timestamp'] >= min_valid_ts) & (df_raw['Timestamp'] <= max_valid_ts)].copy()

    if df_filtered.empty: print("AVISO: Nenhum timestamp válido após filtragem."); return pd.DataFrame()
    print(f"DEBUG: {len(df_raw) - len(df_filtered)} linhas removidas por timestamps inválidos.")
    
    # ### CORREÇÃO: Substitui resample por groupby ###
    # Agrupa pelos timestamps existentes arredondados para milissegundos
    # e pega o último valor registrado para cada grupo/milissegundo.
    df = df_filtered.set_index('Timestamp').sort_index()
    df = df.groupby(df.index.round('ms')).last()

    if df.empty: print("AVISO: DataFrame vazio após agrupamento."); return pd.DataFrame()
    
    # Preenche NaNs curtos (opcional)
    # df = df.ffill(limit=10) # Descomente se quiser preenchimento

    # --- Limpeza e Formatação Final (mesmo código anterior) ---
    df = df.drop(columns=['id', 'timestamp', 'uart_id', 'SourceID'], errors='ignore')
    expected_cols = ['Roll', 'Pitch', 'Yaw', 'Latitude', 'Longitude', 'AltitudeAbs','Voltage', 'Satellites', 'QNE', 'ASI', 'AT', 'Porcent_bat','RPM', 'CHT', 'FuelLevel_dig', 'FuelLevel_anag', 'isVTOL']
    for col in expected_cols:
        if col not in df.columns: df[col] = np.nan
    try: df['Timestamp_str'] = df.index.strftime('%H:%M:%S.%f').str[:-3]
    except AttributeError: df['Timestamp_str'] = None
    if "Yaw" in df.columns and not df["Yaw"].isnull().all(): df["Yaw"] = ((df["Yaw"] + 180) % 360) - 180
    numeric_cols = ['Roll', 'Pitch', 'Yaw', 'Latitude', 'Longitude', 'AltitudeAbs', 'Voltage', 'QNE', 'ASI', 'AT', 'RPM', 'CHT']
    int_cols = ['Satellites', 'Porcent_bat', 'FuelLevel_dig', 'FuelLevel_anag']
    for col in numeric_cols:
         if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
    for col in int_cols:
         if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    df = df.reset_index()

    print(f"INFO: spi.log processado via C Decoder. DataFrame final com {len(df)} linhas.")
    return df


# ===============================================
# === Funções de Parsing Embarcado (original) ===
# ==============================================

def _infer_base_time_from_parent(file_path, fallback_str="2024-01-01-00-00-00"):
    """
    Tenta inferir o timestamp base a partir do nome da pasta-mãe do arquivo.
    Ex.: .../<PASTA>/AFGS_Monitoring.log, com PASTA = '2025-10-31-10-08-56'
    Retorna um pd.Timestamp (naive). Se falhar, usa fallback.
    """
    try:
        parent = os.path.basename(os.path.dirname(os.path.abspath(file_path)))
        # Formato alvo: YYYY-mm-dd-HH-MM-SS
        base = pd.to_datetime(parent, format="%Y-%m-%d-%H-%M-%S", errors="raise")
        return base
    except Exception:
        return pd.to_datetime(fallback_str, format="%Y-%m-%d-%H-%M-%S", errors="coerce")


def parse_afgs_monitoring_log(file_path):
    """
    Lê e desempacota o log embarcado binário 'AFGS_Monitoring.log' (float64, 128 portas)
    e retorna um DataFrame no MESMO formato esperado pelo app (compatível com parse_log_file):
      - Timestamp (datetime)
      - Timestamp_str (HH:MM:SS.mmm)
      - Colunas: Roll, Pitch, Yaw, Latitude, Longitude, AltitudeAbs, ASI, AT, etc.
    Sinais ausentes no log embarcado são criados com NaN para manter compatibilidade.
    """
    import numpy as np
    import pandas as pd

    if not os.path.exists(file_path):
        print(f"ERRO: Arquivo '{file_path}' não encontrado.")
        return pd.DataFrame()

    # --- Definições de portas/typecasting (igual às do seu script) ---
    port_definitions = {
        'single': list(range(1, 51)) + list(range(61, 113)),
        'double': [51, 52] + list(range(113, 124)),
        'boolean': [53, 54, 124],
        'uint16': list(range(55, 59)) + [125, 126, 127],
        'uint8': [59, 60, 128],
    }
    n_signals_map = {'single': 2, 'double': 1, 'boolean': 64, 'uint16': 4, 'uint8': 8}
    dtype_map = {'single': np.float32, 'uint16': np.uint16, 'uint8': np.uint8}

    port_to_type_map = {}
    for dtype, ports in port_definitions.items():
        for port in ports:
            port_to_type_map[port] = dtype

    try:
        # Lê o arquivo binário como float64
        file_bin = np.fromfile(file_path, dtype=np.float64)
        if file_bin.size == 0:
            print("AVISO: AFGS_Monitoring.log vazio ou ilegível.")
            return pd.DataFrame()

        # Cada amostra tem 128 "portas"
        num_logs = file_bin.size // 128
        if num_logs == 0:
            print("AVISO: Tamanho do arquivo não múltiplo de 128 amostras.")
            return pd.DataFrame()

        if file_bin.size % 128 != 0:
            print(f"AVISO: {file_bin.size % 128} floats ignorados no final (não múltiplo de 128).")

        log_data = file_bin[:num_logs * 128].reshape((num_logs, 128))

        # Vetor de tempo (mesmo do seu script): 0.2 s por amostra (5 Hz)
        time_vector = (np.arange(num_logs, dtype=np.float64) * 0.2)

        # Desempacotamento
        headers = ['Time']
        columns = [time_vector]  # lista de vetores 1D

        for k_py in range(128):
            k_matlab = k_py + 1
            if k_matlab not in port_to_type_map:
                continue

            port_type = port_to_type_map[k_matlab]
            n_signals = n_signals_map[port_type]
            col_data_f64 = log_data[:, k_py].copy()

            if port_type == 'boolean':
                # 64 bits por amostra (8 bytes)
                bytes8 = col_data_f64.view(np.uint8).reshape(-1, 8)
                unpacked_bits = np.unpackbits(bytes8, axis=1, bitorder='big')  # (num_logs, 64)
                for m in range(n_signals):
                    default_name = f'Monit_{k_matlab}_S{m+1}'
                    header_name = signal_name_map.get(default_name, default_name)
                    headers.append(header_name)
                    columns.append(unpacked_bits[:, m])
            elif port_type == 'double':
                default_name = f'Monit_{k_matlab}_S1'
                header_name = signal_name_map.get(default_name, default_name)
                headers.append(header_name)
                columns.append(col_data_f64)  # já double
            else:
                dtype = dtype_map[port_type]
                unpacked = col_data_f64.view(dtype).reshape(-1, n_signals)
                for m in range(n_signals):
                    default_name = f'Monit_{k_matlab}_S{m+1}'
                    header_name = signal_name_map.get(default_name, default_name)
                    headers.append(header_name)
                    columns.append(unpacked[:, m])

        # Monta DF base com todos os sinais desempacotados
        final_data_matrix = np.column_stack(columns)
        df_raw = pd.DataFrame(final_data_matrix, columns=headers)

        # ==========================
        # Adaptação ao formato do app
        # ==========================
        # Timestamp sintético: base = nome da pasta (ex.: 2025-10-31-10-08-56) + offset "Time"
        base_time = _infer_base_time_from_parent(file_path)
        df_raw['Timestamp'] = base_time + pd.to_timedelta(df_raw['Time'], unit='s')
        df_raw['Timestamp_str'] = df_raw['Timestamp'].dt.strftime('%H:%M:%S.%f').str[:-3]

        # Mapeia sinais do embarcado -> nomes esperados pelo app
        def rad2deg(series):
            return np.degrees(pd.to_numeric(series, errors='coerce'))

        def yaw_normalize_deg(series_rad):
            yaw_deg = rad2deg(series_rad)
            return ((yaw_deg + 180.0) % 360.0) - 180.0

        # Cria DataFrame de saída (compatível com parse_log_file)
        df_out = pd.DataFrame(index=df_raw.index)
        df_out['Timestamp'] = df_raw['Timestamp']
        df_out['Timestamp_str'] = df_raw['Timestamp_str']

        # Mapas específicos
        # 1) Core já existente (mantido)
        col_map = {
            'AHRS_roll'       : ('Roll',        rad2deg),
            'AHRS_pitch'      : ('Pitch',       rad2deg),
            'AHRS_yaw'        : ('Yaw',         yaw_normalize_deg),

            'Latitude_PA1'    : ('Latitude',    None),
            'Longitude_PA1'   : ('Longitude',   None),
            'Altitude_PA1'    : ('AltitudeAbs', None),

            'ASI'             : ('ASI',         None),
            'Wind_Speed'      : ('WSI',         None),

            'Voltage'         : ('Voltage',     None),
            'RPM'             : ('RPM',         None),
            'CHT'             : ('CHT',         None),

            'FuelLevel_dig'   : ('FuelLevel_dig',   None),
            'FuelLevel_anag'  : ('FuelLevel_anag',  None),

            'Operation_Mode'  : ('ModoVoo',     None),

            'GNSS_NoS'        : ('Satellites',    None),
            'GNSS_LatError'   : ('GNSS_LatError', None),
            'GNSS_LonError'   : ('GNSS_LonError', None),
            'GNSS_AltError'   : ('GNSS_AltError', None),

            'SystemCounter'   : ('SystemCounter', None),
            'GroundLevel'     : ('GroundLevel',   None),
            'ADC_DynamicPressure': ('ADC_DynamicPressure', None),
        }

        # 2) Sinais adicionais (floats) — AHRS/IMU, EKF, DCM, GNSS vel, referências VTOL, etc.
        float_extras = [
            # AHRS pos/vel em cm e taxas
            'AHRS_pos_x_cm', 'AHRS_pos_y_cm', 'AHRS_pos_z_cm',
            'AHRS_vel_x_cm', 'AHRS_vel_y_cm', 'AHRS_vel_z_cm',
            'AHRS_q', 'AHRS_r',
            # Magnetômetro e declinação
            'Mag_X', 'Mag_Y', 'Mag_Z', 'Declination',
            # EKF pos/vel e atitude (EKF_roll/pitch/yaw já em deg no slide)
            'EKF_pos_x', 'EKF_pos_y', 'EKF_pos_z',
            'EKF_vel_x', 'EKF_vel_y', 'EKF_vel_z',
            'EKF_roll', 'EKF_pitch', 'EKF_yaw',
            # DCM atitude
            'DCM_roll', 'DCM_pitch', 'DCM_yaw',
            # GNSS velocidades (N, E, U)
            'VeIN_PA1', 'VeE_PA1', 'VeU_PA1',
            # VTOL refs/targets
            'VTOL_roll_reference', 'VTOL_pitch_reference', 'VTOL_yaw_reference',
            'pos_target_z', 'vel_desired_xy',
            # Outros do bloco FW/asa fixa
            'FW_altitude', 'WindCorrectedCourse', 'FinalPitchRef',
            'AileronR', 'AileronL'
        ]

        for src in float_extras:
            if src in df_raw.columns and src not in col_map:
                col_map[src] = (src, None)  # copia com o mesmo nome

        # 3) Flags/estados discretos que queremos como inteiros (0/1 ou códigos)
        #    (aplicamos round->Int64 com coerção segura)
        int_flags = [
            # Booleans do S128 e isUp
            'GNSS1_PackageFail', 'GNSS2_PackageFail', 'NavSelected', 'GNSS_MSB_bundle',
            'GNSS_Pos_isUp', 'IMU_Mag_isUp', 'MPDC_isUp', 'ADC_isUP', 'EDC_isUp',
            # VTOL / estágios / modos auxiliares
            'in_transition', 'hold_stabilize', 'hold_hover', 'PhaseOne_timer_finished',
            'in_vtol_takeoff', 'in_vtol_land', 'assisted_flight', 'relax_auto',
            'ForceActuationEnable', 'KillSwitch', 'ManualTransition_RPA',
            'disarm_radio', 'FW_Manual', 'From_takeoff', 'CriticalLandStage',
            # Failsafes / externos
            'external_FS', 'internal_FS',
            # Health/flags diversos
            'GNSS_Health', 'EKF_FailSafe', 'EKF_HealthStatus',
        ]

        # 4) Contadores e códigos inteiros
        int_counters = [
            'Mag_ReadCounter', 'EDC_ReadCounter',
            'GNSS2_Pos_ReadCounter', 'GNSS2_Vel_ReadCounter',
            'GNSS1_Pos_ReadCounter', 'GNSS1_Vel_ReadCounter',
            'RC_ReadCounter', 'RC_ReadCounter_2',
            'GNSS_FailNumber', 'RPACheckSum', 'Fail_Number', 'Protection_Number',
            'OpMode_PA1', 'OpMode_from_pilot',  # úteis para debug/telemetria
            'poscontrol_state', 'transition_stage', 'EKF_flags'
        ]

        # ====== Aplicação do mapeamento ======
        # 4.1 Core e floats
        for src, (dst, fn) in col_map.items():
            if src in df_raw.columns:
                df_out[dst] = fn(df_raw[src]) if fn else pd.to_numeric(df_raw[src], errors='coerce')

        # 4.2 Floats extras (identidade já criada acima quando necessário)
        for src in float_extras:
            if src in df_raw.columns and src not in df_out.columns:
                df_out[src] = pd.to_numeric(df_raw[src], errors='coerce')

        # 4.3 Flags/counters como Int64 com coerção segura
        def _to_int64_safe(series):
            s = pd.to_numeric(series, errors='coerce')
            # arredonda valores válidos (caso venham como 0.0/1.0)
            s = s.where(s.isna(), np.rint(s))
            out = pd.Series(pd.NA, index=s.index, dtype='Int64')
            out.loc[s.notna()] = s.loc[s.notna()].astype('int64').values
            return out

        for src in int_flags:
            if src in df_raw.columns:
                df_out[src] = _to_int64_safe(df_raw[src])

        for src in int_counters:
            if src in df_raw.columns:
                df_out[src] = _to_int64_safe(df_raw[src])

        # 5) Completa colunas esperadas pelo app
        expected_cols = [
            'ModoVoo',
            'Roll', 'Pitch', 'Yaw',
            'Latitude', 'Longitude', 'AltitudeAbs',
            'Voltage', 'Satellites', 'QNE', 'ASI', 'AT',
            'Porcent_bat', 'RPM', 'CHT',
            'FuelLevel_dig', 'FuelLevel_anag', 'isVTOL',
            'WSI',
            # Extras úteis sempre presentes no embarcado
            'SystemCounter', 'GroundLevel', 'ADC_DynamicPressure',
            'GNSS_LatError', 'GNSS_LonError', 'GNSS_AltError',
        ]
        for col in expected_cols:
            if col not in df_out.columns:
                df_out[col] = np.nan

        # 6) Tipos finais para o conjunto padrão do app
        numeric_cols = [
            'Roll', 'Pitch', 'Yaw', 'Latitude', 'Longitude', 'AltitudeAbs',
            'Voltage', 'QNE', 'ASI', 'AT', 'RPM', 'CHT', 'WSI',
            'SystemCounter', 'GroundLevel', 'ADC_DynamicPressure',
            'GNSS_LatError', 'GNSS_LonError', 'GNSS_AltError',
        ]
        for col in numeric_cols:
            if col in df_out.columns:
                df_out[col] = pd.to_numeric(df_out[col], errors='coerce')

        int_cols = ['Satellites', 'Porcent_bat', 'FuelLevel_dig', 'FuelLevel_anag', 'ModoVoo']
        for col in int_cols:
            if col in df_out.columns:
                df_out[col] = _to_int64_safe(df_out[col])

        # 7) Ordena por Timestamp e reseta índice
        df_out = df_out.sort_values('Timestamp').reset_index(drop=True)

        print(f"INFO: AFGS_Monitoring.log processado. DataFrame final com {len(df_out)} linhas.")
        return df_out

    except Exception as e:
        print(f"ERRO ao processar AFGS_Monitoring.log: {e}")
        import traceback; traceback.print_exc()
        return pd.DataFrame()

def parse_mat_file(file_path, DEBUG_PRINT=False):
    """
    Lê um arquivo .mat (scipy.loadmat ou HDF5 v7.3 via h5py), desempacota as 128 portas
    usando as mesmas regras do AFGS_Monitoring.log e retorna um DataFrame já no
    formato do app (Timestamp, Timestamp_str e colunas mapeadas manualmente).
    
    Checa arquivo → sai cedo se não existe.
    Tenta scipy.loadmat (clássico) → se falhar, cai pro h5py (v7.3/HDF5) e usa heurísticas para achar DATA (N×P) e TIME (N).
    Normaliza orientações (linhas = tempo), confere N.
    Desempacota portas:
    boolean: explode em 64 bits (flags).
    double: 1 canal.
    single/uint16/uint8: usa view + reshape para obter n_signals por porta.
    Monta df_raw com Time e colunas Monit_* (mapeando para nomes do app).
    Cria Timestamp real a partir do diretório do arquivo + segundos.
    Constrói df_out:
    Aplica conversões (rad→deg, yaw normalizado),
    Copia extras,
    Converte flags/contadores para Int64,
    Preenche colunas esperadas que faltarem,
    Garante tipos numéricos adequados.
    Ordena por tempo e retorna.    
    """

    # -------------- Checagem --------------
    if not os.path.exists(file_path):
        print(f"ERRO: Arquivo .mat '{file_path}' não encontrado.")
        return pd.DataFrame()

    port_definitions = {
        'single': list(range(1, 51)) + list(range(61, 113)),
        'double': [51, 52] + list(range(113, 124)),
        'boolean': [53, 54, 124],
        'uint16': list(range(55, 59)) + [125, 126, 127],
        'uint8': [59, 60, 128],
    }
    n_signals_map = {'single': 2, 'double': 1, 'boolean': 64, 'uint16': 4, 'uint8': 8}
    dtype_map = {'single': np.float32, 'uint16': np.uint16, 'uint8': np.uint8}
    port_to_type_map = {p: t for t, L in port_definitions.items() for p in L}

    def _map_signal_name_local(default_name):
        return signal_name_map.get(default_name, default_name)

    # -------------- Leitura do .mat: scipy primeiro, h5py fallback --------------
    data = None
    time_vector = None
    source = None

    # scipy
    try:
        from scipy.io import loadmat
        mat = loadmat(file_path, squeeze_me=True, struct_as_record=False)
        DAq = mat.get("DAq", None)
        if DAq is None:
            raise ValueError("Campo 'DAq' ausente no .mat")
        afgs_names = [n for n in dir(DAq) if n.startswith("AFGS")]
        if not afgs_names:
            raise ValueError("Campos AFGS_* ausentes no .mat")
        # prioriza 'Primary'
        AFGS = getattr(DAq, sorted(afgs_names, key=lambda k: (0 if "Primary" in k else 1, k))[0])
        data = np.array(AFGS.Data)
        time_vector = np.array(AFGS.Time).reshape(-1)
        if data.ndim == 2 and data.shape[0] < data.shape[1]:
            data = data.T
        source = "scipy.loadmat"
    except Exception:
        # h5py (v7.3)
        try:
            import h5py
        except Exception as e:
            print(f"Falha ao carregar .mat: {e}")
            return pd.DataFrame()

        def is_numeric(dt):
            try:
                return np.issubdtype(dt, np.number)
            except Exception:
                return False

        def resolve_dataset(f, node):
            if isinstance(node, h5py.Dataset):
                refinfo = h5py.check_dtype(ref=node.dtype)
                if refinfo is not None:
                    arr = node[()]
                    flat = np.ravel(arr)
                    for r in flat:
                        if r:
                            return f[r]
                    return None
                return node
            elif isinstance(node, h5py.Group):
                for _, child in node.items():
                    if isinstance(child, h5py.Dataset):
                        return child
                for _, child in node.items():
                    if isinstance(child, h5py.Group):
                        ds = resolve_dataset(f, child)
                        if ds is not None:
                            return ds
                return None
            return None

        def find_time_data_pair(f):
            data_cands, time1d, time2d = [], [], []

            def visitor(name, obj):
                low = name.lower()
                ds = resolve_dataset(f, obj)
                if not isinstance(ds, h5py.Dataset):
                    return
                sh, dt = ds.shape, ds.dtype
                if not is_numeric(dt):
                    return
                if sh == (1, 1):
                    return

                if len(sh) == 1:
                    N = sh[0]; score = 0
                    if "time" in low: score += 5
                    if "/daq" in low: score += 2
                    if "afgs" in low: score += 2
                    time1d.append((score, name, N, ds)); return

                if len(sh) == 2 and 1 in sh and max(sh) > 1:
                    N = max(sh); score = 0
                    if "time" in low: score += 5
                    if "/daq" in low: score += 2
                    if "afgs" in low: score += 2
                    time2d.append((score, name, N, ds)); return

                if len(sh) == 2:
                    m, n = sh; score = 0
                    if "data" in low: score += 5
                    if "/daq" in low: score += 2
                    if "afgs" in low: score += 2
                    if 128 in sh: score += 50
                    if n % 128 == 0: score += 10
                    if m % 128 == 0: score += 5
                    data_cands.append((score, name, m, n, ds))

            f.visititems(visitor)

            if not data_cands:
                raise ValueError("Não encontrei dataset 2D numérico para DATA")
            if not (time1d or time2d):
                raise ValueError("Não encontrei dataset TIME")

            data_cands.sort(key=lambda x: x[0], reverse=True)
            d_score, d_path, m, n, d_ds = data_cands[0]
            D = np.array(d_ds[()])
            if D.ndim == 1: D = D.reshape(-1, 1)
            if D.shape[0] < D.shape[1]: D = D.T
            N, P = D.shape

            time1d.sort(key=lambda x: x[0], reverse=True)
            for t_score, t_name, tN, t_ds in time1d:
                if tN == N:
                    T = np.array(t_ds[()]).reshape(-1)
                    return D, T

            time2d.sort(key=lambda x: x[0], reverse=True)
            for t_score, t_name, tN, t_ds in time2d:
                if tN == N:
                    arr = np.array(t_ds[()]); T = arr.reshape(-1)
                    return D, T

            raise ValueError("Nenhum TIME combina com N de DATA")

        with h5py.File(file_path, "r") as f:
            data, time_vector = find_time_data_pair(f)
            source = "h5py"

    if data is None or time_vector is None:
        print("ERRO: Não foi possível extrair DATA/TIME do .mat.")
        return pd.DataFrame()

    if data.shape[0] != time_vector.shape[0]:
        if data.T.shape[0] == time_vector.shape[0]:
            data = data.T
        else:
            print(f"ERRO: N de TIME {time_vector.shape} não bate com DATA {data.shape}")
            return pd.DataFrame()

    N, n_ports = data.shape
    base = np.ascontiguousarray(data.astype(np.float64, copy=False))

    # -------------- Desempacotamento p/ df_raw (igual embarcado) --------------
    headers = ["Time"]
    cols = [time_vector]

    for k_py in range(n_ports):
        k_matlab = k_py + 1
        if k_matlab not in port_to_type_map:
            continue
        port_type = port_to_type_map[k_matlab]
        n_signals = n_signals_map[port_type]
        col = base[:, k_py].copy()

        if port_type == "boolean":
            # 64 bits por amostra (8 bytes)
            u32 = col.view(np.uint64).view(np.uint32)
            if u32.size != 2 * N:
                u32 = u32.reshape(N, 2)
            bytes_view = u32.view(np.uint8).reshape(N, 8)
            bits = np.unpackbits(bytes_view, axis=1, bitorder="big")[:, -64:]
            unpacked = bits[:, :n_signals]
        elif port_type == "double":
            unpacked = col.reshape(-1, 1)
        else:
            target = dtype_map[port_type]
            viewed = col.view(target)
            try:
                unpacked = viewed.reshape(-1, n_signals)
            except ValueError:
                unpacked = viewed.copy().reshape(-1, n_signals)

        for m in range(n_signals):
            default_name = f"Monit_{k_matlab}_S{m+1}"
            header_name = _map_signal_name_local(default_name)
            headers.append(header_name)
            cols.append(unpacked[:, m])

    df_raw = pd.DataFrame(np.column_stack(cols), columns=headers)

    # -------------- Adaptar ao formato do app (mesmo bloco do parse_afgs_monitoring_log) --------------
    # Timestamp sintético: usa diretório pai como base + Time
    base_time = _infer_base_time_from_parent(file_path)
    df_raw['Timestamp'] = base_time + pd.to_timedelta(pd.to_numeric(df_raw['Time'], errors='coerce'), unit='s')
    df_raw = df_raw.dropna(subset=['Timestamp']).reset_index(drop=True)
    df_raw['Timestamp_str'] = df_raw['Timestamp'].dt.strftime('%H:%M:%S.%f').str[:-3]

    def rad2deg(series):
        return np.degrees(pd.to_numeric(series, errors='coerce'))

    def yaw_normalize_deg(series_rad):
        yaw_deg = rad2deg(series_rad)
        return ((yaw_deg + 180.0) % 360.0) - 180.0

    df_out = pd.DataFrame(index=df_raw.index)
    df_out['Timestamp'] = df_raw['Timestamp']
    df_out['Timestamp_str'] = df_raw['Timestamp_str']

    # 1) Core
    col_map = {
        'AHRS_roll'       : ('Roll',        rad2deg),
        'AHRS_pitch'      : ('Pitch',       rad2deg),
        'AHRS_yaw'        : ('Yaw',         yaw_normalize_deg),

        'Latitude_PA1'    : ('Latitude',    None),
        'Longitude_PA1'   : ('Longitude',   None),
        'Altitude_PA1'    : ('AltitudeAbs', None),

        'ASI'             : ('ASI',         None),
        'Wind_Speed'      : ('WSI',         None),

        'Voltage'         : ('Voltage',     None),
        'RPM'             : ('RPM',         None),
        'CHT'             : ('CHT',         None),

        'FuelLevel_dig'   : ('FuelLevel_dig',   None),
        'FuelLevel_anag'  : ('FuelLevel_anag',  None),

        'Operation_Mode'  : ('ModoVoo',     None),

        'GNSS_NoS'        : ('Satellites',    None),
        'GNSS_LatError'   : ('GNSS_LatError', None),
        'GNSS_LonError'   : ('GNSS_LonError', None),
        'GNSS_AltError'   : ('GNSS_AltError', None),

        'SystemCounter'   : ('SystemCounter', None),
        'GroundLevel'     : ('GroundLevel',   None),
        'ADC_DynamicPressure': ('ADC_DynamicPressure', None),
    }

    float_extras = [
        'AHRS_pos_x_cm', 'AHRS_pos_y_cm', 'AHRS_pos_z_cm',
        'AHRS_vel_x_cm', 'AHRS_vel_y_cm', 'AHRS_vel_z_cm',
        'AHRS_q', 'AHRS_r',
        'Mag_X', 'Mag_Y', 'Mag_Z', 'Declination',
        'EKF_pos_x', 'EKF_pos_y', 'EKF_pos_z',
        'EKF_vel_x', 'EKF_vel_y', 'EKF_vel_z',
        'EKF_roll', 'EKF_pitch', 'EKF_yaw',
        'DCM_roll', 'DCM_pitch', 'DCM_yaw',
        'VeIN_PA1', 'VeE_PA1', 'VeU_PA1',
        'VTOL_roll_reference', 'VTOL_pitch_reference', 'VTOL_yaw_reference',
        'pos_target_z', 'vel_desired_xy',
        'FW_altitude', 'WindCorrectedCourse', 'FinalPitchRef',
        'AileronR', 'AileronL'
    ]
    for src in float_extras:
        if src in df_raw.columns and src not in col_map:
            col_map[src] = (src, None)

    int_flags = [
        'GNSS1_PackageFail', 'GNSS2_PackageFail', 'NavSelected', 'GNSS_MSB_bundle',
        'GNSS_Pos_isUp', 'IMU_Mag_isUp', 'MPDC_isUp', 'ADC_isUP', 'EDC_isUp',
        'in_transition', 'hold_stabilize', 'hold_hover', 'PhaseOne_timer_finished',
        'in_vtol_takeoff', 'in_vtol_land', 'assisted_flight', 'relax_auto',
        'ForceActuationEnable', 'KillSwitch', 'ManualTransition_RPA',
        'disarm_radio', 'FW_Manual', 'From_takeoff', 'CriticalLandStage',
        'external_FS', 'internal_FS',
        'GNSS_Health', 'EKF_FailSafe', 'EKF_HealthStatus',
    ]
    int_counters = [
        'Mag_ReadCounter', 'EDC_ReadCounter',
        'GNSS2_Pos_ReadCounter', 'GNSS2_Vel_ReadCounter',
        'GNSS1_Pos_ReadCounter', 'GNSS1_Vel_ReadCounter',
        'RC_ReadCounter', 'RC_ReadCounter_2',
        'GNSS_FailNumber', 'RPACheckSum', 'Fail_Number', 'Protection_Number',
        'OpMode_PA1', 'OpMode_from_pilot',
        'poscontrol_state', 'transition_stage', 'EKF_flags'
    ]

    # aplica core + floats
    for src, (dst, fn) in col_map.items():
        if src in df_raw.columns:
            df_out[dst] = fn(df_raw[src]) if fn else pd.to_numeric(df_raw[src], errors='coerce')
    for src in float_extras:
        if src in df_raw.columns and src not in df_out.columns:
            df_out[src] = pd.to_numeric(df_raw[src], errors='coerce')

    # inteiros seguros
    def _to_int64_safe(series):
        s = pd.to_numeric(series, errors='coerce')
        s = s.where(s.isna(), np.rint(s))
        out = pd.Series(pd.NA, index=s.index, dtype='Int64')
        out.loc[s.notna()] = s.loc[s.notna()].astype('int64').values
        return out

    for src in int_flags:
        if src in df_raw.columns:
            df_out[src] = _to_int64_safe(df_raw[src])
    for src in int_counters:
        if src in df_raw.columns:
            df_out[src] = _to_int64_safe(df_raw[src])

    # completa colunas do app
    expected_cols = [
        'ModoVoo',
        'Roll', 'Pitch', 'Yaw',
        'Latitude', 'Longitude', 'AltitudeAbs',
        'Voltage', 'Satellites', 'QNE', 'ASI', 'AT',
        'Porcent_bat', 'RPM', 'CHT',
        'FuelLevel_dig', 'FuelLevel_anag', 'isVTOL',
        'WSI',
        'SystemCounter', 'GroundLevel', 'ADC_DynamicPressure',
        'GNSS_LatError', 'GNSS_LonError', 'GNSS_AltError',
    ]
    for col in expected_cols:
        if col not in df_out.columns:
            df_out[col] = np.nan

    # numéricos e inteiros padrão
    numeric_cols = [
        'Roll', 'Pitch', 'Yaw', 'Latitude', 'Longitude', 'AltitudeAbs',
        'Voltage', 'QNE', 'ASI', 'AT', 'RPM', 'CHT', 'WSI',
        'SystemCounter', 'GroundLevel', 'ADC_DynamicPressure',
        'GNSS_LatError', 'GNSS_LonError', 'GNSS_AltError',
    ]
    for col in numeric_cols:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors='coerce')

    int_cols = ['Satellites', 'Porcent_bat', 'FuelLevel_dig', 'FuelLevel_anag', 'ModoVoo']
    for col in int_cols:
        if col in df_out.columns:
            df_out[col] = _to_int64_safe(df_out[col])

    df_out = df_out.sort_values('Timestamp').reset_index(drop=True)
    print(f"INFO: .mat processado ({source}). DataFrame final com {len(df_out)} linhas.")
    return df_out

# ==========================================
# === Funções de Parsing XCockpit ===
# ==========================================

def parse_log_file(file_path):
    """
    Analisa o arquivo de log para extrair todos os dados de telemetria
    de forma robusta à ordem dos campos.
    """
    key_to_name = {
        '?': 'ModoVoo', 'P': 'Pitch', 'R': 'Roll', 'Y': 'Yaw', 'H': 'AltitudeAbs',
        'S': 'ASI', 'Q': 'QNE', 'u': 'WSI', 'o': 'WindDirection', '%': 'GNSS_Select',
        'n': 'RPM', 't': 'CHT', 's': 'FuelLevel_dig', '¢': 'AT', '=': 'FuelLevel_anag',
        'N': 'Latitude', 'E': 'Longitude', 'V': 'VSI', 'U': 'GSI', 'D': 'Alt_geoidal',
        'O': 'Path_angle', 'I': 'RTK_Status', 'G': 'Satellites', 'F': 'Sat_use',
        'h': 'Incert_Long', 'v': 'Incert_pos_z', 'y': 'Spoofing', 'x': 'Jamming',
        'a': 'Voltage', 'e': 'Filt_VDC', 'b': 'Porcent_bat', "'": 'ForceG',
        "¨": 'IsFlying', '@': 'N_ForcedLanding', 'c': 'IsForcedLanding',
        'd': 'isVTOL', 'l': 'Elevator', 'r': 'Aileron', 'f': 'FailNumber',
        'p': 'ProtectionNumber', 'º': 'VTOL_vbat', 'B': 'AFGNS_Select',
    }
    
    keys_str = ''.join(re.escape(k) for k in key_to_name.keys())
    pattern = re.compile(f"([{keys_str}])(-?\\d+(?:\\.\\d+)?)")

    data = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                ts_match = re.match(r"^(\d{2}:\d{2}:\d{2}\.\d{3})", line)
                if not ts_match:
                    continue
                
                timestamp_str = ts_match.group(1)
                
                row_data = {name: np.nan for name in key_to_name.values()}
                row_data["Timestamp_str"] = timestamp_str

                matches = pattern.findall(line)
                
                for key, value in matches:
                    col_name = key_to_name.get(key)
                    if col_name:
                        try:
                            row_data[col_name] = float(value)
                        except (ValueError, TypeError):
                            pass
                
                data.append(row_data)

    except Exception as e:
        print(f"Erro ao ler o arquivo: {e}")
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    base_time = _infer_base_time_from_parent(file_path)
    time_deltas = pd.to_timedelta(df['Timestamp_str'], errors='coerce')
    df['Timestamp'] = (base_time + time_deltas).where(time_deltas.notna())
    df = df.dropna(subset=['Timestamp']).reset_index(drop=True)
    if not df.empty:
        df['Timestamp_str'] = df['Timestamp'].dt.strftime('%H:%M:%S.%f').str[:-3]
    
    if "Yaw" in df.columns and not df["Yaw"].isnull().all():
        df["Yaw"] = ((df["Yaw"] + 180) % 360) - 180
        
    return df

def parse_csv_file(file_path):
    """Analisa CSV no formato Monit_X_SY e converte para DataFrame compatível com o app."""
    try:
        df = pd.read_csv(file_path)

        base_time = _infer_base_time_from_parent(file_path)
        # Em muitos CSVs o passo é ~1s; se o seu CSV tiver uma coluna de tempo, pode trocar por ela.
        df["Timestamp"] = base_time + pd.to_timedelta(np.arange(len(df)), unit="s")
        df["Timestamp_str"] = df["Timestamp"].dt.strftime('%H:%M:%S.%f').str[:-3]

        column_map = {
            "Monit_1_S1": "Roll", "Monit_2_S1": "Pitch", "Monit_3_S1": "Yaw",
            "Monit_4_SY": "AltitudeAbs", "Monit_28_SY": "Latitude",
            "Monit_29_SY": "Longitude", "Monit_32_SY": "Voltage",
            "Monit_33_SY": "Satellites",
        }

        for old, new in column_map.items():
            if old in df.columns:
                df.rename(columns={old: new}, inplace=True)
            else:
                df[new] = np.nan
        
        if "isVTOL" not in df.columns:
            df["isVTOL"] = np.nan

        return df
    except Exception as e:
        print(f"Erro ao ler CSV: {e}")
        return pd.DataFrame()

# ==========================================
# === Funções de Parsing Datalogger ===
# ==========================================

def parse_datalogger_file(file_path):
    """
    Lê um arquivo de datalogger no formato:

        Time[ms];pwmL[us];curL[mA];volL[mV];pwmR[us];curR[mA];volR[mV];strini[uint10]
        43065;2376;0;0;0;2;176;6
        ...

    e devolve um DataFrame compatível com o app, contendo:

    - Timestamp (datetime) e Timestamp_str (HH:MM:SS.mmm)
    - Voltage  -> tensão da bateria (V), no mesmo nome usado pelos outros parsers
    - Novas colunas específicas do datalogger:
        * ServoL_PWM_us
        * ServoR_PWM_us
        * ServoL_Current_mA
        * ServoR_Current_mA
        * ServoL_Voltage_V
        * ServoR_Voltage_V
        * Battery_Current_A   (corrente da bateria, strini * 210 / 1023)

    As demais colunas padrão do app (Roll, Pitch, Yaw, etc.) são criadas com NaN
    para manter compatibilidade com o restante do código.
    """
    if not os.path.exists(file_path):
        print(f"ERRO: Arquivo de datalogger '{file_path}' não encontrado.")
        return pd.DataFrame()

    try:
        # separador ';'
        df_raw = pd.read_csv(file_path, sep=';', engine='python')
    except Exception as e:
        print(f"ERRO ao ler datalogger '{file_path}': {e}")
        return pd.DataFrame()

    # Renomeia colunas
    rename_map = {
        'Time[ms]'      : 'Time_ms',
        'pwmL[us]'      : 'pwmL_us',
        'curL[mA]'      : 'curL_mA',
        'volL[mV]'      : 'volL_mV',
        'pwmR[us]'      : 'pwmR_us',
        'curR[mA]'      : 'curR_mA',
        'volR[mV]'      : 'volR_mV',
        'strini[uint10]': 'strini',
    }
    df_raw.rename(columns=rename_map, inplace=True)

    # Garante que as colunas críticas existam
    if 'Time_ms' not in df_raw.columns:
        print("ERRO: coluna 'Time[ms]' ausente no datalogger.")
        return pd.DataFrame()

    # Converte numéricos
    num_cols = ['Time_ms', 'pwmL_us', 'curL_mA', 'volL_mV',
                'pwmR_us', 'curR_mA', 'volR_mV', 'strini']
    for c in num_cols:
        if c in df_raw.columns:
            df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce')

    df_raw = df_raw.dropna(subset=['Time_ms']).reset_index(drop=True)
    if df_raw.empty:
        print("AVISO: datalogger sem linhas válidas após conversão de Time_ms.")
        return pd.DataFrame()

    # Timestamp baseado no nome da pasta (igual aos outros parsers) + tempo em ms
    base_time = _infer_base_time_from_parent(file_path)
    if pd.isna(base_time):
        # fallback bem definido se o nome da pasta não tiver timestamp
        base_time = pd.Timestamp('2024-01-01 00:00:00')

    df_raw['Timestamp'] = base_time + pd.to_timedelta(df_raw['Time_ms'], unit='ms')
    df_raw['Timestamp_str'] = df_raw['Timestamp'].dt.strftime('%H:%M:%S.%f').str[:-3]

    # DataFrame de saída no formato do app
    df_out = pd.DataFrame(index=df_raw.index)
    df_out['Timestamp'] = df_raw['Timestamp']
    df_out['Timestamp_str'] = df_raw['Timestamp_str']

    # ------------------------------
    # Tensão da bateria (Voltage)
    # ------------------------------
    # Usa o maior valor entre volL e volR como aproximação da tensão do barramento,
    # em volts (mV -> V), para manter compatibilidade com os outros parsers.
    voltage_series = None
    if 'volL_mV' in df_raw.columns and 'volR_mV' in df_raw.columns:
        voltage_series = np.maximum(df_raw['volL_mV'], df_raw['volR_mV']) / 1000.0
    elif 'volL_mV' in df_raw.columns:
        voltage_series = df_raw['volL_mV'] / 1000.0
    elif 'volR_mV' in df_raw.columns:
        voltage_series = df_raw['volR_mV'] / 1000.0

    if voltage_series is not None:
        df_out['Voltage'] = voltage_series
    else:
        df_out['Voltage'] = np.nan

    # -------------------------------------------
    # Novos dados específicos do datalogger
    # -------------------------------------------
    # Comando PWM servo esquerdo e direito
    if 'pwmL_us' in df_raw.columns:
        df_out['ServoL_PWM_us'] = df_raw['pwmL_us']
    if 'pwmR_us' in df_raw.columns:
        df_out['ServoR_PWM_us'] = df_raw['pwmR_us']

    # Corrente servo esquerdo e direito (mA)
    if 'curL_mA' in df_raw.columns:
        df_out['ServoL_Current_mA'] = df_raw['curL_mA']
    if 'curR_mA' in df_raw.columns:
        df_out['ServoR_Current_mA'] = df_raw['curR_mA']

    # Tensão no servo esquerdo e direito (V)
    if 'volL_mV' in df_raw.columns:
        df_out['ServoL_Voltage_V'] = df_raw['volL_mV'] / 1000.0
    if 'volR_mV' in df_raw.columns:
        df_out['ServoR_Voltage_V'] = df_raw['volR_mV'] / 1000.0

    # Corrente na bateria (A) a partir de strini (uint10)
    if 'strini' in df_raw.columns:
        df_out['Battery_Current_A'] = df_raw['strini'] * (210.0 / 1023.0)

    # -------------------------------------------
    # Completa colunas padrão do app com NaN
    # (mesmo contrato dos outros parsers)
    # -------------------------------------------
    expected_cols = [
        'ModoVoo',
        'Roll', 'Pitch', 'Yaw',
        'Latitude', 'Longitude', 'AltitudeAbs',
        'Voltage', 'Satellites', 'QNE', 'ASI', 'AT',
        'Porcent_bat', 'RPM', 'CHT',
        'FuelLevel_dig', 'FuelLevel_anag', 'isVTOL',
    ]
    for col in expected_cols:
        if col not in df_out.columns:
            df_out[col] = np.nan

    # Garante tipos numéricos coerentes nas colunas padrão
    numeric_cols = [
        'Roll', 'Pitch', 'Yaw', 'Latitude', 'Longitude', 'AltitudeAbs',
        'Voltage', 'QNE', 'ASI', 'AT', 'RPM', 'CHT',
        'FuelLevel_dig', 'FuelLevel_anag',
    ]
    for col in numeric_cols:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors='coerce')

    int_cols = ['Satellites', 'Porcent_bat', 'ModoVoo']
    for col in int_cols:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors='coerce').round()
            df_out[col] = df_out[col].astype('Int64')

    df_out = df_out.sort_values('Timestamp').reset_index(drop=True)
    print(f"INFO: Datalogger processado. DataFrame final com {len(df_out)} linhas.")
    return df_out

# ==========================================================
# === Classe Worker Modificada para Busca Hierárquica ===
# ==========================================================
class LogProcessingWorker(QObject):
    finished = pyqtSignal(dict)
    progress = pyqtSignal(int)          # porcentagem
    log_loaded = pyqtSignal(str, str)   # (log_name, log_type)
    error = pyqtSignal(str)

    def __init__(self, root_path):
        super().__init__()
        self.root_path = root_path
        self._is_running = True

    def run(self):
        try:
            loaded_logs = {}

            # -------------------------------------------
            # Conta diretórios + prepara lista de itens
            # -------------------------------------------
            try:
                sub_items = list(os.scandir(self.root_path))
                dir_items = [item for item in sub_items if item.is_dir()]
                # +1 para considerar a própria pasta raiz como "unidade" de processamento
                total_units = len(dir_items) + 1
            except Exception as count_e:
                print(f"Erro ao contar diretórios: {count_e}")
                sub_items = []
                dir_items = []
                total_units = 0
                # Sinaliza que não dá para estimar progresso
                self.progress.emit(-1)

            processed_count = 0

            # -------------------------------------------
            # Função interna para processar UMA pasta
            # (serve tanto pra raiz quanto pras subpastas)
            # -------------------------------------------
            def process_folder(folder_path, folder_label):
                nonlocal processed_count, loaded_logs, total_units

                if not self._is_running:
                    return

                df_main = pd.DataFrame()
                main_type = "Nenhum"
                main_filename = ""

                # 1. Procura por GCFS_AIRPLANE_*.log (Xcockpit)
                try:
                    for filename in os.listdir(folder_path):
                        if filename.startswith("GCFS_AIRPLANE_") and filename.lower().endswith(".log"):
                            log_file_path = os.path.join(folder_path, filename)
                            df_main = parse_log_file(log_file_path)
                            if not df_main.empty:
                                df_main.attrs["log_type"] = "Xcockpit (.log)"
                                main_type = "Xcockpit (.log)"
                                main_filename = filename
                            break
                except Exception as list_e:
                    print(f"Erro ao listar arquivos .log em {folder_path}: {list_e}")

                # 2. Se não encontrou Xcockpit .log, procura por GCFS_AIRPLANE_*.csv
                if df_main.empty:
                    try:
                        for filename in os.listdir(folder_path):
                            if filename.startswith("GCFS_AIRPLANE_") and filename.lower().endswith(".csv"):
                                log_file_path = os.path.join(folder_path, filename)
                                df_main = parse_csv_file(log_file_path)
                                if not df_main.empty:
                                    df_main.attrs["log_type"] = "CSV (.csv)"
                                    main_type = "CSV (.csv)"
                                    main_filename = filename
                                break
                    except Exception as list_e:
                        print(f"Erro ao listar arquivos .csv em {folder_path}: {list_e}")

                # 3. Se não encontrou Xcockpit nem CSV, procura por spi.log e chama o C Decoder
                if df_main.empty:
                    spi_path = os.path.join(folder_path, "spi.log")
                    if os.path.exists(spi_path):
                        df_main = parse_spi_log_via_c(spi_path)
                        if not df_main.empty:
                            df_main.attrs["log_type"] = "Embarcado (spi.log via C)"
                            main_type = "Embarcado (spi.log via C)"
                            main_filename = "spi.log"

                # 4. Se ainda não achou nada, procura o log embarcado AFGS_Monitoring.log
                if df_main.empty:
                    afgs_path = os.path.join(folder_path, "AFGS_Monitoring.log")
                    if os.path.exists(afgs_path):
                        df_main = parse_afgs_monitoring_log(afgs_path)
                        if not df_main.empty:
                            df_main.attrs["log_type"] = "Embarcado (AFGS_Monitoring.log)"
                            main_type = "Embarcado (AFGS_Monitoring.log)"
                            main_filename = "AFGS_Monitoring.log"

                # 5. Busca .mat (embarcado em .mat - mesmo mapeamento do AFGS.log)
                if df_main.empty:
                    try:
                        for filename in os.listdir(folder_path):
                            if filename.lower().endswith(".mat"):
                                mat_path = os.path.join(folder_path, filename)
                                df_main = parse_mat_file(mat_path)
                                if not df_main.empty:
                                    df_main.attrs["log_type"] = "Embarcado (.mat)"
                                    main_type = "Embarcado (.mat)"
                                    main_filename = filename
                                    break
                    except Exception as list_e:
                        print(f"Erro ao listar/ler .mat em {folder_path}: {list_e}")

                # 6. Busca logXX.csv (Datalogger) – pode haver vários na mesma pasta
                try:
                    for filename in os.listdir(folder_path):
                        if filename.lower().startswith("log") and filename.lower().endswith(".csv"):
                            log_path = os.path.join(folder_path, filename)
                            df_d = parse_datalogger_file(log_path)
                            if not df_d.empty:
                                df_d.attrs["log_type"] = "Datalogger (logXX.csv)"
                                # Nome exibido: <pasta> - <arquivo>
                                display_name = f"{folder_label} - {filename}"
                                loaded_logs[display_name] = df_d
                                self.log_loaded.emit(display_name, "Datalogger (logXX.csv)")
                except Exception as list_e:
                    print(f"Erro ao ler datalogger .csv em {folder_path}: {list_e}")

                # Se encontrou um log "principal" (telemetria), registra também
                if not df_main.empty:
                    # Se já existe chave com o mesmo nome, desambigua
                    display_name = folder_label
                    if display_name in loaded_logs:
                        display_name = f"{folder_label} - {main_filename or main_type}"
                    loaded_logs[display_name] = df_main
                    self.log_loaded.emit(display_name, main_type)

                # Atualiza progresso para essa unidade (pasta ou raiz)
                processed_count += 1
                if total_units > 0:
                    percent = int((processed_count / total_units) * 100)
                    self.progress.emit(percent)

            # -------------------------------------------
            # 1º: processa a própria pasta raiz
            # -------------------------------------------
            root_label = os.path.basename(os.path.normpath(self.root_path)) or self.root_path
            process_folder(self.root_path, root_label)

            # -------------------------------------------
            # 2º: processa cada subdiretório direto
            # -------------------------------------------
            for item in dir_items:
                if not self._is_running:
                    break
                process_folder(item.path, item.name)

            # Garante que a barra chegue a 100% no final, mesmo com arredondamentos
            if self._is_running and total_units > 0:
                self.progress.emit(100)

            if self._is_running:
                self.finished.emit(loaded_logs)

        except Exception as e:
            self.error.emit(f"Falha CRÍTICA no processamento dos logs: {e}")
            import traceback
            traceback.print_exc()

    def stop(self):
        self._is_running = False