import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
from scipy.io import loadmat

# --- 1. DICIONÁRIO DE SINAIS (Mapeamento) ---
# Adicionado com base na sua lista.
# NOTE: Corrigi 'Monit_113' para 'Monit_113_S1', etc., 
# para corresponder à lógica do script.
signal_name_map = {
    'Monit_4_S1': 'Motor_1',
    'Monit_4_S2': 'Motor_2',
    'Monit_5_S1': 'Motor_3',
    'Monit_5_S2': 'Motor_4',
    'Monit_9_S2': 'Elevator',
    'Monit_10_S1': 'Engine',
    'Monit_10_S2': 'Aileron',
    'Monit_11_S1': 'Fail_Number',
    'Monit_53_S19': 'Parachute',
    'Monit_58_S1': 'Protection_Number',
    'Monit_59_S2': 'Operation_Mode',
    'Monit_61_S2': 'AHRS_pos_x_cm',
    'Monit_62_S1': 'AHRS_pos_y_cm',
    'Monit_62_S2': 'AHRS_pos_z_cm',
    'Monit_63_S1': 'AHRS_vel_x_cm',
    'Monit_63_S2': 'AHRS_vel_y_cm',
    'Monit_64_S1': 'AHRS_vel_z_cm',
    'Monit_64_S2': 'acel_x',
    'Monit_65_S1': 'acel_y',
    'Monit_65_S2': 'acel_z',
    'Monit_66_S1': 'AHRS_roll',
    'Monit_66_S2': 'AHRS_pitch',
    'Monit_67_S1': 'AHRS_yaw',
    'Monit_69_S1': 'EKF_HealthStatus',
    'Monit_70_S1': 'GNSS_LatError',
    'Monit_70_S2': 'GNSS_LonError',
    'Monit_71_S1': 'GNSS_AltError',
    'Monit_71_S2': 'ASI',
    'Monit_74_S2': 'Mag_X',
    'Monit_75_S1': 'Mag_Y',
    'Monit_75_S2': 'Mag_Z',
    'Monit_77_S2': 'Wind_Speed',
    'Monit_84_S2': 'Contador_ADC',
    'Monit_87_S2': 'Temperatura_ADC',
    'Monit_105_S1': 'Temperatura_SPDM',
    'Monit_113_S1': 'Latitude_PA1',  # Corrigido de 'Monit_113'
    'Monit_114_S1': 'Longitude_PA1', # Corrigido de 'Monit_114'
    'Monit_115_S1': 'Altitude_PA1',  # Corrigido de 'Monit_115'
    'Monit_124_S9': 'WingConnected'
}


# --- Função de Plotagem  ---
def plot_results(df, csv_path):
    """
    Recebe o DataFrame com os dados desempacotados e plota os
    sinais de interesse, usando os nomes amigáveis.
    """
    try:
        import matplotlib.pyplot as plt
        
        print("Calculando e plotando os dados...")
        
        # --- 1. Extração de Dados (Usando novos nomes) ---
        pi = np.pi
        time = df['Time'].to_numpy()
        
        # Atitude
        # (Sinais de referência não estavam no mapa, então mantemos o nome original)
        Roll_ref = df['Monit_48_S1'].to_numpy()
        Pitch_ref = df['Monit_45_S1'].to_numpy()
        Roll_rad = df['AHRS_roll'].to_numpy()
        Pitch_rad = df['AHRS_pitch'].to_numpy()
        Yaw_rad = df['AHRS_yaw'].to_numpy()

        # Posição e Velocidade
        Pos_x_cm = df['AHRS_pos_x_cm'].to_numpy()
        Pos_y_cm = df['AHRS_pos_y_cm'].to_numpy()
        Vel_x_cm = df['AHRS_vel_x_cm'].to_numpy()
        Vel_y_cm = df['AHRS_vel_y_cm'].to_numpy()
        ASI = df['ASI'].to_numpy()

        # Atuadores
        Ail_rad = df['Aileron'].to_numpy()
        Elev_rad = df['Elevator'].to_numpy()
        
        # VTOL e Modo
        VTOL_1 = df['Motor_1'].to_numpy()
        VTOL_2 = df['Motor_2'].to_numpy()
        VTOL_3 = df['Motor_3'].to_numpy()
        VTOL_4 = df['Motor_4'].to_numpy()
        OperationMode = df['Operation_Mode'].to_numpy()

        # --- NOVOS SINAIS PARA PLOTAR ---
        acel_x = df['acel_x'].to_numpy()
        acel_y = df['acel_y'].to_numpy()
        acel_z = df['acel_z'].to_numpy()

        Mag_X = df['Mag_X'].to_numpy()
        Mag_Y = df['Mag_Y'].to_numpy()
        Mag_Z = df['Mag_Z'].to_numpy()
        
        EKF_Health = df['EKF_HealthStatus'].to_numpy()
        GNSS_LatError = df['GNSS_LatError'].to_numpy()
        GNSS_LonError = df['GNSS_LonError'].to_numpy()

        Temp_ADC = df['Temperatura_ADC'].to_numpy()
        Temp_SPDM = df['Temperatura_SPDM'].to_numpy()

        # --- 2. Cálculos (Agora tudo é NumPy) ---
        
        Roll = Roll_rad * 180 / pi
        Pitch = Pitch_rad * 180 / pi
        Yaw = np.mod(Yaw_rad, 2 * pi) * 180 / pi 

        Pos_x = Pos_x_cm / 100
        Pos_y = Pos_y_cm / 100
        Vel_x = Vel_x_cm / 100
        Vel_y = Vel_y_cm / 100
        
        GSI = np.hypot(Vel_x, Vel_y)
        
        Ail = Ail_rad * 180 / pi
        Elev = Elev_rad * 180 / pi
        
        ElevR = np.clip(Elev + Ail, -20, 10)
        ElevL = np.clip(Elev - Ail, -20, 10)
        
        Ail_adj = (ElevR - ElevL) / 2
        Elev_adj = (ElevR + ElevL) / 2
        
        # --- 3. Criação dos Plots (Mais plots adicionados) ---
        print("Gerando figura...")
        # Aumentado de 7 para 11 subplots
        fig, axs = plt.subplots(11, 1, figsize=(15, 30), sharex=True)
        fig.suptitle(f'Análise do Log: {os.path.basename(csv_path)}', fontsize=16)

        # 1. Atitude (Roll, Pitch)
        axs[0].plot(time, Roll, label='AHRS_roll (graus)')
        axs[0].plot(time, Roll_ref, label='Roll Ref (graus)', linestyle='--')
        axs[0].plot(time, Pitch, label='AHRS_pitch (graus)')
        axs[0].plot(time, Pitch_ref, label='Pitch Ref (graus)', linestyle='--')
        axs[0].set_ylabel('Atitude (graus)')
        axs[0].legend(loc='best')
        axs[0].grid(True)

        # 2. Yaw
        axs[1].plot(time, Yaw, label='AHRS_yaw (graus)')
        axs[1].set_ylabel('Yaw (graus)')
        axs[1].legend(loc='best')
        axs[1].grid(True)

        # 3. Posição (X, Y)
        axs[2].plot(time, Pos_x, label='AHRS_pos_x (m)')
        axs[2].plot(time, Pos_y, label='AHRS_pos_y (m)')
        axs[2].set_ylabel('Posição (m)')
        axs[2].legend(loc='best')
        axs[2].grid(True)

        # 4. Velocidades (Groundspeed, Airspeed)
        axs[3].plot(time, GSI, label='Vel. Solo (GSI) (m/s)')
        axs[3].plot(time, ASI, label='ASI (m/s)')
        axs[3].set_ylabel('Velocidade (m/s)')
        axs[3].legend(loc='best')
        axs[3].grid(True)

        # 5. Atuadores (Aileron, Elevon)
        axs[4].plot(time, Ail_adj, label='Aileron (ajustado, graus)')
        axs[4].plot(time, Elev_adj, label='Elevon (ajustado, graus)')
        axs[4].set_ylabel('Atuadores (graus)')
        axs[4].legend(loc='best')
        axs[4].grid(True)

        # 6. Motores VTOL
        axs[5].plot(time, VTOL_1, label='Motor_1')
        axs[5].plot(time, VTOL_2, label='Motor_2')
        axs[5].plot(time, VTOL_3, label='Motor_3')
        axs[5].plot(time, VTOL_4, label='Motor_4')
        axs[5].set_ylabel('Sinais Motores VTOL')
        axs[5].legend(loc='best')
        axs[5].grid(True)

        # 7. Operation Mode
        axs[6].plot(time, OperationMode, label='Operation_Mode', drawstyle='steps-post')
        axs[6].set_ylabel('Modo de Operação')
        axs[6].legend(loc='best')
        axs[6].grid(True)
        
        # --- NOVOS PLOTS ---
        
        # 8. Aceleração
        axs[7].plot(time, acel_x, label='acel_x')
        axs[7].plot(time, acel_y, label='acel_y')
        axs[7].plot(time, acel_z, label='acel_z')
        axs[7].set_ylabel('Aceleração (m/s²)')
        axs[7].legend(loc='best')
        axs[7].grid(True)
        
        # 9. Magnetômetro
        axs[8].plot(time, Mag_X, label='Mag_X')
        axs[8].plot(time, Mag_Y, label='Mag_Y')
        axs[8].plot(time, Mag_Z, label='Mag_Z')
        axs[8].set_ylabel('Magnetômetro')
        axs[8].legend(loc='best')
        axs[8].grid(True)

        # 10. Saúde EKF / Erro GNSS
        axs[9].plot(time, EKF_Health, label='EKF_HealthStatus', drawstyle='steps-post')
        axs[9].plot(time, GNSS_LatError, label='GNSS_LatError (m)')
        axs[9].plot(time, GNSS_LonError, label='GNSS_LonError (m)')
        axs[9].set_ylabel('Saúde EKF / Erro GNSS')
        axs[9].legend(loc='best')
        axs[9].grid(True)

        # 11. Temperaturas
        axs[10].plot(time, Temp_ADC, label='Temperatura_ADC (C)')
        axs[10].plot(time, Temp_SPDM, label='Temperatura_SPDM (C)')
        axs[10].set_ylabel('Temperatura (°C)')
        axs[10].set_xlabel('Tempo (s)') # Label de tempo agora no último plot
        axs[10].legend(loc='best')
        axs[10].grid(True)
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.98]) # Ajusta para o título
        print("Mostrando plots... Feche a janela para finalizar.")
        plt.show() # Mostra o gráfico e pausa o script até a janela ser fechada

    except KeyError as e:
        print(f"Erro de Plot: A coluna {e} não foi encontrada no CSV.", file=sys.stderr)
        messagebox.showerror("Erro no Plot", f"Não foi possível plotar: A coluna {e} não foi encontrada.\nVerifique se o nome está correto no 'signal_name_map' e no CSV.")
    except Exception as e:
        print(f"Ocorreu um erro durante o plot: {e}", file=sys.stderr)
        messagebox.showerror("Erro no Plot", f"Ocorreu um erro inesperado ao plotar:\n{e}")

def process_mat_to_unpacked_csv(mat_path):
    """
    Lê um arquivo .mat exportado do MATLAB (estrutura DAq.AFGS_Primary),
    desempacota as portas e gera .csv e gráficos.
    """
    port_definitions = {
        'single': list(range(1, 51)) + list(range(61, 113)),
        'double': [51, 52] + list(range(113, 124)),
        'boolean': [53, 54, 124],
        'uint16': list(range(55, 59)) + [125, 126, 127],
        'uint8': [59, 60, 128]
    }
    n_signals_map = {
        'single': 2, 'double': 1, 'boolean': 64, 'uint16': 4, 'uint8': 8
    }
    dtype_map = {'single': np.float32, 'uint16': np.uint16, 'uint8': np.uint8}

    port_to_type_map = {}
    for dtype, ports in port_definitions.items():
        for port in ports:
            port_to_type_map[port] = dtype

    try:
        print(f"Lendo arquivo .mat: {mat_path}")
        mat_data = loadmat(mat_path, squeeze_me=True, struct_as_record=False)

        DAq = mat_data.get('DAq', None)
        if DAq is None:
            raise ValueError("Estrutura 'DAq' não encontrada no arquivo .mat.")

        field_names = [f for f in dir(DAq) if 'AFGS' in f]
        if not field_names:
            raise ValueError("Campo 'AFGS_Primary' não encontrado dentro de 'DAq'.")
        AFGS = getattr(DAq, field_names[0])

        data = AFGS.Data
        time_vector = AFGS.Time
        print(f"Shape dos dados: {data.shape}")

        num_logs, n_ports = data.shape
        all_unpacked_data = [time_vector]
        headers = ['Time']

        for k_py in range(n_ports):
            k_matlab = k_py + 1
            if k_matlab not in port_to_type_map:
                continue
            port_type = port_to_type_map[k_matlab]
            n_signals = n_signals_map[port_type]

            col_data = data[:, k_py]

            if port_type == 'boolean':
                col_data_u32 = col_data.view(np.uint32)
                packed = np.reshape(col_data_u32, (-1, 1))
                unpacked_data = np.unpackbits(
                    packed.view(np.uint8), axis=1, bitorder='big'
                )[:, -n_signals:]
            elif port_type == 'double':
                unpacked_data = col_data.reshape(-1, 1)
            else:
                dtype = dtype_map[port_type]
                unpacked_data = col_data.view(dtype).reshape(-1, n_signals)

            for m in range(n_signals):
                default_name = f'Monit_{k_matlab}_S{m + 1}'
                header_name = signal_name_map.get(default_name, default_name)
                headers.append(header_name)
                all_unpacked_data.append(unpacked_data[:, m])

        final_data_matrix = np.column_stack(all_unpacked_data)
        df = pd.DataFrame(final_data_matrix, columns=headers)

        output_csv_path = mat_path.rsplit('.', 1)[0] + '.csv'
        df.to_csv(output_csv_path, index=False, lineterminator='\n')
        print(f"Arquivo CSV salvo: {output_csv_path}")

        plot_results(df, output_csv_path)
        messagebox.showinfo("Sucesso", f"Processo concluído!\nArquivo salvo como {os.path.basename(output_csv_path)}")

    except Exception as e:
        messagebox.showerror("Erro", f"Falha ao processar arquivo .mat:\n{e}")
        print(f"Erro MAT: {e}")

# --- Função Principal de Conversão ---
def process_log_to_unpacked_csv():
    """
    Script Python completo para:
    1. Ler um arquivo .log binário (float64).
    2. Desempacotar os dados com base nas regras de portas (typecasting).
    3. Salvar o resultado final como um arquivo .csv desempacotado.
    4. Chamar a função de plotagem.
    """
    
    # 1. Definições das portas (traduzidas da "Area do usuario" do MATLAB)
    port_definitions = {
        'single': list(range(1, 51)) + list(range(61, 113)),
        'double': [51, 52] + list(range(113, 124)),
        'boolean': [53, 54, 124],
        'uint16': list(range(55, 59)) + [125, 126, 127],
        'uint8': [59, 60, 128]
    }

    n_signals_map = {
        'single': 2, 'double': 1, 'boolean': 64, 'uint16': 4, 'uint8': 8
    }

    dtype_map = {
        'single': np.float32, 'uint16': np.uint16, 'uint8': np.uint8
    }

    port_to_type_map = {}
    total_ports = 0
    for dtype, ports in port_definitions.items():
        for port in ports:
            port_to_type_map[port] = dtype
            total_ports += 1
            
    if total_ports != 128:
        print(f"Aviso: O mapeamento de portas definiu {total_ports} portas, mas 128 era esperado.")

    try:
        # 2. Configurar a janela de diálogo para seleção de arquivo
        root = tk.Tk()
        root.withdraw()
        
        log_path = filedialog.askopenfilename(
            title='Escolha o arquivo de log binário (.log)',
            filetypes=[('Log files', '*.log'), ('All files', '*.*')]
        )
        
        if not log_path:
            print("Nenhuma arquivo selecionado. Encerrando.")
            root.destroy()
            return

        print(f"Processando arquivo: {log_path}")

        # 4. Leitura do arquivo binário
        file_bin = np.fromfile(log_path, dtype=np.float64)
        
        if file_bin.size == 0:
            messagebox.showerror("Erro", "O arquivo está vazio ou não pôde ser lido.")
            root.destroy()
            return

        # 5. Reorganizar os dados
        num_logs = file_bin.size // 128
        
        if file_bin.size % 128 != 0:
            print(f"Aviso: O tamanho do arquivo não é um múltiplo perfeito de 128. "
                  f"Ignorando {file_bin.size % 128} bytes/floats no final.")
        
        log_data = file_bin[:num_logs * 128].reshape((num_logs, 128))

        # 6. Criar o vetor de tempo
        time_vector = (np.arange(num_logs, dtype=np.float64) * 0.2)

        # 7. Processo de Desempacotamento
        all_unpacked_data = [time_vector]
        headers = ['Time']

        for k_py in range(128):
            k_matlab = k_py + 1
            
            if k_matlab not in port_to_type_map:
                print(f"Aviso: Porta {k_matlab} não definida no mapeamento. Pulando.")
                continue
                
            port_type = port_to_type_map[k_matlab]
            n_signals = n_signals_map[port_type]
            
            # .copy() é crucial para garantir memória contínua
            col_data_f64 = log_data[:, k_py].copy() 
            
            if port_type == 'boolean':
                unpacked_data = np.unpackbits(
                    col_data_f64.view(np.uint8).reshape(-1, 8), 
                    axis=1, 
                    bitorder='big'
                )
            elif port_type == 'double':
                unpacked_data = col_data_f64.reshape(-1, 1)
            else:
                dtype = dtype_map[port_type]
                unpacked_data = col_data_f64.view(dtype).reshape(-1, n_signals)
            
            # --- LÓGICA DE MAPEAMENTO DE HEADER ATUALIZADA ---
            for m in range(n_signals):
                # 1. Cria o nome padrão
                default_name = f'Monit_{k_matlab}_S{m + 1}'
                
                # 2. Pega o nome do mapa se existir, senão usa o padrão
                header_name = signal_name_map.get(default_name, default_name)

                headers.append(header_name)
                all_unpacked_data.append(unpacked_data[:, m])
        # --- FIM DA LÓGICA ATUALIZADA ---

        # 8. Criar o DataFrame e Salvar em CSV
        print(f"Total de colunas desempacotadas (incluindo Time): {len(headers)}")
        
        final_data_matrix = np.stack(all_unpacked_data, axis=1)
        df = pd.DataFrame(final_data_matrix, columns=headers)
        
        output_csv_path = log_path.rsplit('.', 1)[0] + '.csv'
        df.to_csv(output_csv_path, index=False, lineterminator='\n')
        
        print(f"Arquivo CSV desempacotado salvo com sucesso em: {output_csv_path}")
        
        # --- 9. CHAMAR A FUNÇÃO DE PLOTAGEM ---
        plot_results(df, output_csv_path)

        # 10. Mostrar mensagem de "Done!" final
        messagebox.showinfo("Sucesso", f"Processo concluído!\nArquivo salvo como {os.path.basename(output_csv_path)}")
        root.destroy()

    except Exception as e:
        print(f"Ocorreu um erro: {e}", file=sys.stderr)
        messagebox.showerror("Erro", f"Ocorreu um erro:\n{e}")
        if 'root' in locals():
            root.destroy()

# --- Executar a função ---
if __name__ == "__main__":
    # Instalar pandas e matplotlib se não estiverem instalados
    try:
        import pandas as pd
    except ImportError:
        print("Módulo 'pandas' não encontrado. Tentando instalar...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas"])
        print("'pandas' instalado com sucesso.")
        
    try:
        import matplotlib
    except ImportError:
        print("Módulo 'matplotlib' não encontrado. Tentando instalar...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib"])
        print("'matplotlib' instalado com sucesso.")
        
    process_log_to_unpacked_csv()