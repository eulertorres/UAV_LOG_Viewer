# src/widgets/standard_plots_widget.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QGroupBox, QRadioButton)
from PyQt6.QtCore import Qt
import pandas as pd
import numpy as np
from geopy.distance import geodesic
import matplotlib.dates

# Importações do Matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

class StandardPlotsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.df = pd.DataFrame() # DataFrame ativo
        self.current_log_name = ""
        self.lined = {}
        self._sync_axes = []
        self._syncing = False
        self.vlines = []

        layout = QVBoxLayout(self)
        
        # Grupo de Radio Buttons
        self.plot_selector_group = QGroupBox("Gráficos")
        plot_selector_layout = QHBoxLayout()
        self.radio_voltage = QRadioButton("Tensão")
        self.radio_wind_variability = QRadioButton("Variabilidade Vento (Vel/Dir)")
        self.radio_rpy = QRadioButton("Roll / Pitch / Yaw")
        self.radio_variance = QRadioButton("Variância RPY/Alt")
        self.radio_position = QRadioButton("Posicionamento")
        
        self.radios = [self.radio_voltage, self.radio_wind_variability, self.radio_rpy, self.radio_variance, self.radio_position]
        self.radio_voltage.setChecked(True)
        
        for r in self.radios:
            r.toggled.connect(self.update_plot) # Conecta ao método local
            plot_selector_layout.addWidget(r)
        
        self.plot_selector_group.setLayout(plot_selector_layout)
        layout.addWidget(self.plot_selector_group)
        
        # Figura e Canvas do Matplotlib
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.figure.canvas.mpl_connect("pick_event", self.on_pick) # Conecta ao método local
        self.toolbar = NavigationToolbar(self.canvas, self) # Toolbar como filho deste widget
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)

    def load_dataframe(self, df, log_name = ""):
        """Recebe o DataFrame da janela principal."""
        self.df = df
        self.current_log_name = log_name
        self.update_plot() # Atualiza o gráfico com os novos dados

    def update_cursor(self, timestamp):
        """Atualiza a linha vertical (cursor) no gráfico."""
        if self.df.empty or not self.vlines:
            return
        for vline in self.vlines:
            try:
                # Verifica se o vline e seus eixos ainda são válidos
                if vline and vline.axes and vline.figure:
                    vline.set_xdata([timestamp])
                    vline.set_visible(True)
                else:
                    # Se inválido, remove da lista (pode acontecer se a figura for limpa)
                    self.vlines.remove(vline)
            except Exception as e:
                # Em caso de erro inesperado, apenas imprime e continua
                print(f"Erro ao atualizar vline: {e}")
                try:
                    self.vlines.remove(vline)
                except ValueError:
                    pass # Já pode ter sido removido

        # Tenta redesenhar apenas se houver vlines válidas
        if self.vlines:
            self.canvas.draw_idle()


    # --- Funções de Plot (Movidas para cá e CORRIGIDAS com .to_numpy()) ---
    
    def plot_voltage(self):
        if 'Voltage' not in self.df.columns:
            QMessageBox.warning(self, "Erro", "A coluna 'Voltage' não foi encontrada.")
            return

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        # ### CORRIGIDO ###
        ax.plot(self.df['Timestamp'].to_numpy(), self.df['Voltage'].to_numpy(), marker='.', linestyle='-', label='Tensão (V)')
        ax.set_title(f'Tensão da Bateria ({self.current_log_name})', fontsize=14);
        ax.set_xlabel('Timestamp')
        ax.set_ylabel('Tensão (V)')
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)

        leg = ax.legend()
        self.lined = {legline: origline for legline, origline in zip(leg.get_lines(), ax.get_lines())}
        for legline in self.lined: legline.set_picker(True)

        self.sync_x_axes([ax])
        self.figure.tight_layout()
        self.add_vlines()
        self.canvas.draw()

    # def plot_wind_variability(self):
        # required_wind = ["WSI", "WindDirection"]
        # has_wind_data = all(c in self.df.columns and not self.df[c].isnull().all() for c in required_wind)
        # has_path_angle = 'Path_angle' in self.df.columns and not self.df['Path_angle'].isnull().all()

        # if not has_wind_data and not has_path_angle:
             # QMessageBox.warning(self, "Erro", "Colunas 'WSI'/'WindDirection' ou 'Path_angle' não encontradas ou vazias.")
             # return
        
        # self.figure.clear()
        # # Define número de linhas baseado nos dados disponíveis
        # nrows = sum([1 if has_wind_data else 0, 1 if has_wind_data else 0, 1 if has_path_angle else 0])
        # if nrows == 0: return # Segurança extra
        
        # # Ajusta height_ratios se houver menos plots
        # height_ratios = [1.0, 1.0, 0.8] 
        # if nrows == 2:
             # if has_wind_data and has_path_angle: height_ratios = [1.0, 0.8] # Vento + Path
             # elif has_wind_data: height_ratios = [1.0, 1.0] # Só vento
        # elif nrows == 1: height_ratios = [1.0] # Só Path

        # gs = self.figure.add_gridspec(nrows=nrows, ncols=1, height_ratios=height_ratios[:nrows])
        
        # axes_to_sync = []
        # plot_idx = 0 # Índice para adicionar subplots
        # self.lined = {} # Reseta a legenda interativa

        # # --- Plot Variabilidade Vento (se houver dados) ---
        # if has_wind_data:
            # d_wind = self.df.dropna(subset=required_wind)
            # window = 30 
            # wsi_var = d_wind["WSI"].rolling(window).var()
            # wsi_std = d_wind["WSI"].rolling(window).std()
            # winddir_var = d_wind["WindDirection"].rolling(window).var()
            # winddir_std = d_wind["WindDirection"].rolling(window).std()

            # # -- Subplot Velocidade --
            # ax1 = self.figure.add_subplot(gs[plot_idx, 0]); plot_idx += 1
            # color_var = 'tab:blue'; color_std = 'tab:cyan'
            # ax1.set_ylabel('Var WSI (m²/s²)', color=color_var, fontsize=9)
            # ln1 = ax1.plot(d_wind['Timestamp'].to_numpy(), wsi_var.to_numpy(), color=color_var, label=f'Var WSI (J={window})')
            # ax1.tick_params(axis='y', labelcolor=color_var, labelsize=8); ax1.grid(True, linestyle=':', alpha=0.6)
            # ax1b = ax1.twinx(); ax1b.set_ylabel('Std Dev WSI (m/s)', color=color_std, fontsize=9)
            # ln2 = ax1b.plot(d_wind['Timestamp'].to_numpy(), wsi_std.to_numpy(), color=color_std, label=f'Std Dev WSI (J={window})', linestyle='--')
            # ax1b.tick_params(axis='y', labelcolor=color_std, labelsize=8)
            # ax1.set_title(f"Variabilidade Velocidade Vento ({self.current_log_name})", fontsize=11) # Título atualizado
            # lns1 = ln1 + ln2; labs1 = [l.get_label() for l in lns1]; leg1 = ax1.legend(lns1, labs1, loc='best', fontsize=7)
            # self.lined.update({l: o for l, o in zip(leg1.get_lines(), lns1)})
            # axes_to_sync.append(ax1)

            # # -- Subplot Direção --
            # ax2 = self.figure.add_subplot(gs[plot_idx, 0]); plot_idx += 1
            # color_var_dir = 'tab:red'; color_std_dir = 'tab:orange'
            # ax2.set_ylabel('Var Direção (°²)', color=color_var_dir, fontsize=9)
            # ln3 = ax2.plot(d_wind['Timestamp'].to_numpy(), winddir_var.to_numpy(), color=color_var_dir, label=f'Var Dir (J={window})')
            # ax2.tick_params(axis='y', labelcolor=color_var_dir, labelsize=8); ax2.grid(True, linestyle=':', alpha=0.6)
            # ax2b = ax2.twinx(); ax2b.set_ylabel('Std Dev Direção (°)', color=color_std_dir, fontsize=9)
            # ln4 = ax2b.plot(d_wind['Timestamp'].to_numpy(), winddir_std.to_numpy(), color=color_std_dir, label=f'Std Dev Dir (J={window})', linestyle='--')
            # ax2b.tick_params(axis='y', labelcolor=color_std_dir, labelsize=8)
            # ax2.set_title(f"Variabilidade Direção Vento ({self.current_log_name})", fontsize=11) # Título atualizado
            # lns2 = ln3 + ln4; labs2 = [l.get_label() for l in lns2]; leg2 = ax2.legend(lns2, labs2, loc='best', fontsize=7)
            # self.lined.update({l: o for l, o in zip(leg2.get_lines(), lns2)})
            # axes_to_sync.append(ax2)
        
        # # --- Plot Path Angle (se houver dados) ---
        # if has_path_angle:
            # ax3 = self.figure.add_subplot(gs[plot_idx, 0]); plot_idx += 1
            # d_path = self.df.dropna(subset=['Path_angle'])
            # color_path = 'tab:green'
            # ln5 = ax3.plot(d_path['Timestamp'].to_numpy(), d_path['Path_angle'].to_numpy(), color=color_path, label='Path Angle')
            # ax3.set_ylabel('Path Angle (°)', color=color_path, fontsize=9)
            # ax3.tick_params(axis='y', labelcolor=color_path, labelsize=8)
            # ax3.grid(True, linestyle=':', alpha=0.6)
            # ax3.set_title(f"Ângulo de Trajetória ({self.current_log_name})", fontsize=11) # Título atualizado
            # leg3 = ax3.legend(loc='best', fontsize=7)
            # self.lined.update({l: o for l, o in zip(leg3.get_lines(), ln5)})
            # axes_to_sync.append(ax3)

        # # Configura eixo X apenas no último gráfico visível
        # if axes_to_sync:
            # axes_to_sync[-1].set_xlabel('Timestamp', fontsize=9)
            
        # # Torna todas as linhas da legenda clicáveis
        # for legline in self.lined: legline.set_picker(True)

        # self.sync_x_axes(axes_to_sync)
        # self.figure.tight_layout(pad=1.0, h_pad=0.3) # Ajusta espaçamento
        # self.add_vlines()
        # self.canvas.draw()

    def plot_wind_variability(self):
        # ### MÉTODO MODIFICADO (Cálculo de Vento Corrigido) ###
        required_wind = ["WSI", "WindDirection"]
        has_wind_data = all(c in self.df.columns and not self.df[c].isnull().all() for c in required_wind)
        has_path_angle = 'Path_angle' in self.df.columns and not self.df['Path_angle'].isnull().all()

        if not has_wind_data and not has_path_angle:
             QMessageBox.warning(self, "Erro", "Colunas 'WSI'/'WindDirection' ou 'Path_angle' não encontradas ou vazias.")
             return
        
        self.figure.clear()
        nrows = sum([1 if has_wind_data else 0, 1 if has_wind_data else 0, 1 if has_path_angle else 0])
        if nrows == 0: return 
        
        height_ratios = [1.0, 1.0, 0.8] 
        if nrows == 2:
             if has_wind_data and has_path_angle: height_ratios = [1.0, 0.8]
             elif has_wind_data: height_ratios = [1.0, 1.0]
        elif nrows == 1: height_ratios = [1.0] 

        gs = self.figure.add_gridspec(nrows=nrows, ncols=1, height_ratios=height_ratios[:nrows])
        
        axes_to_sync = []
        plot_idx = 0 
        self.lined = {} 

        # --- Plot Variabilidade Vento (se houver dados) ---
        if has_wind_data:
            d_wind = self.df.dropna(subset=required_wind)
            window = 30 
            
            # --- Cálculo de Velocidade (WSI) - Inalterado ---
            wsi_var = d_wind["WSI"].rolling(window).var()
            wsi_std = d_wind["WSI"].rolling(window).std()
            
            # --- Cálculo de Direção (Circular) - CORRIGIDO ---
            wind_rad = np.deg2rad(d_wind["WindDirection"]) # Converte para radianos
            wind_cos = np.cos(wind_rad)
            wind_sin = np.sin(wind_rad)
            mean_cos = wind_cos.rolling(window).mean() # Média dos componentes X
            mean_sin = wind_sin.rolling(window).mean() # Média dos componentes Y
            
            # R (Comprimento do Vetor Médio)
            # np.clip para evitar R > 1 por erros de ponto flutuante
            r_squared = np.clip(np.sqrt(mean_cos**2 + mean_sin**2), 0, 1) 
            r = np.sqrt(np.clip(r_squared, 0, 1)) # Clip o valor *antes* do sqrt para garantir
            
            # V (Variância Circular) = 1 - R. (Varia de 0 a 1)
            winddir_var_circular = 1 - r 
            
            # S (Desvio Padrão Circular) = sqrt(-2 * ln(R))
            # Adiciona 'epsilon' (valor muito pequeno) para evitar log(0)
            epsilon = 1e-15
            winddir_std_rad = np.sqrt(-2 * np.log(r + epsilon))
            winddir_std_deg = np.rad2deg(winddir_std_rad) # Converte para graus

            # -- Subplot Velocidade --
            ax1 = self.figure.add_subplot(gs[plot_idx, 0]); plot_idx += 1
            color_var = 'tab:blue'; color_std = 'tab:cyan'
            ax1.set_ylabel('Var WSI (m²/s²)', color=color_var, fontsize=9)
            ln1 = ax1.plot(d_wind['Timestamp'].to_numpy(), wsi_var.to_numpy(), color=color_var, label=f'Var WSI (J={window})')
            ax1.tick_params(axis='y', labelcolor=color_var, labelsize=8); ax1.grid(True, linestyle=':', alpha=0.6)
            ax1b = ax1.twinx(); ax1b.set_ylabel('Std Dev WSI (m/s)', color=color_std, fontsize=9)
            ln2 = ax1b.plot(d_wind['Timestamp'].to_numpy(), wsi_std.to_numpy(), color=color_std, label=f'Std Dev WSI (J={window})', linestyle='--')
            ax1b.tick_params(axis='y', labelcolor=color_std, labelsize=8)
            ax1.set_title(f"Variabilidade Velocidade Vento ({self.current_log_name})", fontsize=11)
            lns1 = ln1 + ln2; labs1 = [l.get_label() for l in lns1]; leg1 = ax1.legend(lns1, labs1, loc='best', fontsize=7)
            self.lined.update({l: o for l, o in zip(leg1.get_lines(), lns1)})
            axes_to_sync.append(ax1)

            # -- Subplot Direção (com dados corrigidos) --
            ax2 = self.figure.add_subplot(gs[plot_idx, 0]); plot_idx += 1
            color_var_dir = 'tab:red'; color_std_dir = 'tab:orange'
            # ### ALTERADO ### Label do eixo Y para refletir 0-1
            ax2.set_ylabel('Var Circular Dir (0-1)', color=color_var_dir, fontsize=9) 
            # ### ALTERADO ### Plota a variância circular (1-R)
            ln3 = ax2.plot(d_wind['Timestamp'].to_numpy(), winddir_var_circular.to_numpy(), color=color_var_dir, label=f'Var Dir (Circular, J={window})')
            ax2.tick_params(axis='y', labelcolor=color_var_dir, labelsize=8); ax2.grid(True, linestyle=':', alpha=0.6)
            #ax2.set_ylim(-0.05, 1.05) # Força o eixo da variância circular a ficar entre 0 e 1
            
            ax2b = ax2.twinx(); ax2b.set_ylabel('Std Dev Circular (°)', color=color_std_dir, fontsize=9) # Label atualizado
            # ### ALTERADO ### Plota o desvio padrão circular em graus
            ln4 = ax2b.plot(d_wind['Timestamp'].to_numpy(), winddir_std_deg.to_numpy(), color=color_std_dir, label=f'Std Dev Dir (Circular, J={window})', linestyle='--')
            ax2b.tick_params(axis='y', labelcolor=color_std_dir, labelsize=8)
            ax2.set_title(f"Variabilidade Direção Vento ({self.current_log_name})", fontsize=11)
            lns2 = ln3 + ln4; labs2 = [l.get_label() for l in lns2]; leg2 = ax2.legend(lns2, labs2, loc='best', fontsize=7)
            self.lined.update({l: o for l, o in zip(leg2.get_lines(), lns2)})
            axes_to_sync.append(ax2)
        
        # --- Plot Path Angle (inalterado) ---
        if has_path_angle:
            ax3 = self.figure.add_subplot(gs[plot_idx, 0]); plot_idx += 1
            d_path = self.df.dropna(subset=['Path_angle'])
            color_path = 'tab:green'
            ln5 = ax3.plot(d_path['Timestamp'].to_numpy(), d_path['Path_angle'].to_numpy(), color=color_path, label='Path Angle')
            ax3.set_ylabel('Path Angle (°)', color=color_path, fontsize=9)
            ax3.tick_params(axis='y', labelcolor=color_path, labelsize=8)
            ax3.grid(True, linestyle=':', alpha=0.6)
            ax3.set_title(f"Ângulo de Trajetória ({self.current_log_name})", fontsize=11)
            leg3 = ax3.legend(loc='best', fontsize=7)
            self.lined.update({l: o for l, o in zip(leg3.get_lines(), ln5)})
            axes_to_sync.append(ax3)

        if axes_to_sync: axes_to_sync[-1].set_xlabel('Timestamp', fontsize=9)
        for legline in self.lined: legline.set_picker(True)

        self.sync_x_axes(axes_to_sync)
        self.figure.tight_layout(pad=1.0, h_pad=0.3) # h_pad pequeno
        self.add_vlines()
        self.canvas.draw()

    def plot_variance_rpy_alt(self):
        required = ["Roll","Pitch","Yaw","AltitudeAbs"]; 
        if not all(c in self.df.columns for c in required): 
             QMessageBox.warning(self, "Erro", "Colunas de Atitude ou Altitude não encontradas."); return
        d = self.df.dropna(subset=required); window = 50
        if d.empty: 
             QMessageBox.information(self, "Info", "Nenhum dado de RPY/Altitude válido."); return

        roll_var=d["Roll"].rolling(window).var(); pitch_var=d["Pitch"].rolling(window).var(); yaw_var=d["Yaw"].rolling(window).var(); alt_var=d["AltitudeAbs"].rolling(window).var()
        
        self.figure.clear(); gs=self.figure.add_gridspec(2, 3, height_ratios=[1.0, 1.4]); ax_roll=self.figure.add_subplot(gs[0,0]); ax_pitch=self.figure.add_subplot(gs[0,1]); ax_yaw=self.figure.add_subplot(gs[0,2]); ax_all=self.figure.add_subplot(gs[1,:])
        
        # ### CORRIGIDO ###
        ax_roll.plot(d['Timestamp'].to_numpy(), roll_var.to_numpy(), color='#1f77b4'); 
        ax_pitch.plot(d['Timestamp'].to_numpy(), pitch_var.to_numpy(), color='#2ca02c'); 
        ax_yaw.plot(d['Timestamp'].to_numpy(), yaw_var.to_numpy(), color='#d62728')
        
        for ax, t in [(ax_roll,"Var Roll"), (ax_pitch,"Var Pitch"), (ax_yaw,"Var Yaw")]: ax.set_title(t, fontsize=11); ax.set_ylabel("Var"); ax.grid(True, linestyle='--')
        
        # ### CORRIGIDO ###
        ax_all.plot(d['Timestamp'].to_numpy(), roll_var.to_numpy(), label='Var Roll', color='#1f77b4'); 
        ax_all.plot(d['Timestamp'].to_numpy(), pitch_var.to_numpy(), label='Var Pitch', color='#2ca02c'); 
        ax_all.plot(d['Timestamp'].to_numpy(), yaw_var.to_numpy(), label='Var Yaw', color='#d62728'); 
        ax_all.plot(d['Timestamp'].to_numpy(), alt_var.to_numpy(), label='Var Alt', color='#9467bd', linestyle='--')
        
        ax_all.set_title(f"Variância RPY e Alt ({self.current_log_name})", fontsize=12); # Título atualizado
        ax_all.set_xlabel("Timestamp"); ax_all.set_ylabel("Variância"); ax_all.grid(True, linestyle='--')
        leg=ax_all.legend(); self.lined={l:o for l,o in zip(leg.get_lines(),ax_all.get_lines())}; [l.set_picker(True) for l in self.lined]
        self.sync_x_axes([ax_roll, ax_pitch, ax_yaw, ax_all]); self.figure.tight_layout(); self.add_vlines(); self.canvas.draw()

    def plot_rpy(self):
        req = ["Roll", "Pitch", "Yaw"]; 
        if not all(c in self.df.columns for c in req): 
             QMessageBox.warning(self, "Erro", "Colunas Roll, Pitch ou Yaw não encontradas."); return
        d = self.df.dropna(subset=req)
        if d.empty: 
             QMessageBox.information(self, "Info", "Nenhum dado RPY válido."); return

        self.figure.clear(); gs=self.figure.add_gridspec(3, 3, height_ratios=[1.0, 1.4, 0.8]); ax_roll=self.figure.add_subplot(gs[0,0]); ax_pitch=self.figure.add_subplot(gs[0,1]); ax_yaw=self.figure.add_subplot(gs[0,2]); ax_all=self.figure.add_subplot(gs[1,:]); ax_vtol=self.figure.add_subplot(gs[2,:]); axes_to_sync=[ax_roll,ax_pitch,ax_yaw,ax_all]
        
        # ### CORRIGIDO ###
        ax_roll.plot(d['Timestamp'].to_numpy(),d['Roll'].to_numpy(),marker='.',linestyle='-',label='Roll',color='#1f77b4'); 
        ax_pitch.plot(d['Timestamp'].to_numpy(),d['Pitch'].to_numpy(),marker='.',linestyle='-',label='Pitch',color='#2ca02c'); 
        ax_yaw.plot(d['Timestamp'].to_numpy(),d['Yaw'].to_numpy(),marker='.',linestyle='-',label='Yaw',color='#d62728')
        
        for ax,t in [(ax_roll,"Roll(°)"),(ax_pitch,"Pitch(°)"),(ax_yaw,"Yaw(°)")]: ax.set_title(t,fontsize=11); ax.set_ylabel("°"); ax.grid(True,linestyle='--')
        
        # ### CORRIGIDO ###
        ax_all.plot(d['Timestamp'].to_numpy(),d['Roll'].to_numpy(),label='Roll',color='#1f77b4'); 
        ax_all.plot(d['Timestamp'].to_numpy(),d['Pitch'].to_numpy(),label='Pitch',color='#2ca02c'); 
        ax_all.plot(d['Timestamp'].to_numpy(),d['Yaw'].to_numpy(),label='Yaw',color='#d62728')
        
        ax_alt=None;
        if "AltitudeAbs" in d.columns: 
             ax_alt=ax_all.twinx(); 
             # ### CORRIGIDO ###
             ax_alt.plot(d['Timestamp'].to_numpy(),d['AltitudeAbs'].to_numpy(),label='Altitude(m)',color='#9467bd',linestyle='--'); 
             ax_alt.set_ylabel("Altitude (m)")
             
        ax_all.set_title(f"RPY e Altitude ({self.current_log_name})", fontsize=12); # Título atualizado
        ax_all.set_xlabel("Timestamp"); ax_all.set_ylabel("Ângulos (°)"); ax_all.grid(True,linestyle='--')
        
        if "isVTOL" in d.columns and not d["isVTOL"].isnull().all(): 
             # ### CORRIGIDO ###
             ax_vtol.plot(d['Timestamp'].to_numpy(),d['isVTOL'].to_numpy(),label='isVTOL',color='#ff7f0e',marker='.',drawstyle='steps-post'); 
             ax_vtol.set_title("Modo VTOL"); ax_vtol.set_ylabel("Estado"); ax_vtol.set_yticks([0,1]); ax_vtol.grid(True,axis='y'); axes_to_sync.append(ax_vtol)
        else: ax_vtol.text(0.5,0.5,"'isVTOL' não disponível",ha="center",va="center")
        
        self.lined={}; lines,labels=ax_all.get_legend_handles_labels(); all_lines=list(ax_all.get_lines())
        if ax_alt is not None: l2h,l2l=ax_alt.get_legend_handles_labels(); lines+=l2h; labels+=l2l; all_lines+=list(ax_alt.get_lines())
        leg=ax_all.legend(lines,labels);
        for l,o in zip(leg.get_lines(),all_lines): l.set_picker(True); self.lined[l]=o
        if "isVTOL" in d.columns and not d["isVTOL"].isnull().all(): leg_vtol=ax_vtol.legend(); [l.set_picker(True) for l in leg_vtol.get_lines()]
        
        self.sync_x_axes(axes_to_sync); self.figure.tight_layout(); self.add_vlines(); self.canvas.draw()

    def plot_position(self):
        req = ["Latitude","Longitude","AltitudeAbs"]; 
        if not all(c in self.df.columns for c in req): 
             QMessageBox.warning(self, "Erro", "Dados de posição/altitude não encontrados."); return
        d = self.df.dropna(subset=req)
        if d.empty: return

        lat0,lon0,alt0=d.iloc[0][req]; dists=np.array([geodesic((lat0,lon0),(lat,lon)).meters for lat,lon in zip(d["Latitude"],d["Longitude"])]); alt_rel=(d["AltitudeAbs"]-alt0).to_numpy()
        
        self.figure.clear(); ax1=self.figure.add_subplot(211); ax2=self.figure.add_subplot(212)
        
        # ### CORRIGIDO ###
        ax1.plot(d["Timestamp"].to_numpy(),dists,color="blue",label="Dist. Horiz.(m)"); 
        ax1.set_ylabel("Dist(m)"); ax1.set_title("Dist. da Posição Inicial"); ax1.grid(True)
        
        # ### CORRIGIDO ###
        ax2.plot(d["Timestamp"].to_numpy(),alt_rel,color="green",label="Alt. Relativa(m)"); 
        ax2.set_ylabel("Alt(m)"); ax2.set_xlabel("Timestamp"); ax2.set_title("Alt. Relativa à Inicial"); ax2.grid(True)
        
        leg1=ax1.legend(); leg2=ax2.legend(); self.lined={}
        for l,o in zip(leg1.get_lines(),ax1.get_lines()): l.set_picker(True); self.lined[l]=o
        for l,o in zip(leg2.get_lines(),ax2.get_lines()): l.set_picker(True); self.lined[l]=o
        
        self.sync_x_axes([ax1,ax2]); self.figure.tight_layout(); self.add_vlines(); self.canvas.draw()
        
    # --- Funções Auxiliares de Plot (Movidas para cá) ---
    
    def on_pick(self, event):
        legline=event.artist
        origline=self.lined.get(legline)
        if origline:
            origline.set_visible(not origline.get_visible())
            legline.set_alpha(1.0 if origline.get_visible() else 0.2)
            self.canvas.draw()

    def sync_x_axes(self, axes):
        self._sync_axes = axes
        self._syncing = False
        
        # Desconecta quaisquer callbacks antigos dos eixos da figura atual
        # Isso previne múltiplas conexões se sync_x_axes for chamado várias vezes
        connected_callbacks = {}
        for ax in self.figure.get_axes():
            cids = ax.callbacks.callbacks.get('xlim_changed', {})
            for cid, callback in cids.items():
                 # Guardamos o ID da conexão para poder desconectar depois
                 if callback.__func__ == self._on_xlim_changed.__func__:
                     connected_callbacks[ax] = cid
        for ax, cid in connected_callbacks.items():
            try:
                ax.callbacks.disconnect(cid)
            except KeyError: # Pode já ter sido desconectado
                pass
                
        # Conecta os novos callbacks
        for ax in axes: 
            ax.callbacks.connect("xlim_changed", self._on_xlim_changed)

    def _on_xlim_changed(self, ax):
        if self._syncing or not hasattr(self, '_sync_axes'): return # Verificação extra
        self._syncing = True
        xmin, xmax = ax.get_xlim()
        # Itera sobre os eixos que DEVEM ser sincronizados (_sync_axes)
        for other in self._sync_axes: 
            if other is not ax and other.get_xlim() != (xmin, xmax): 
                other.set_xlim(xmin, xmax)
        self._syncing = False
        self.canvas.draw_idle()

    def add_vlines(self):
        """Adiciona ou atualiza as linhas verticais (cursores)."""
        self.vlines.clear() # Limpa as referências antigas
        if self.df.empty: return
        try:
            initial_ts = self.df['Timestamp'].iloc[0]
            # Adiciona vlines a todos os eixos da figura atual
            for ax in self.figure.get_axes():
                vline = ax.axvline(initial_ts, color='r', linestyle='--', lw=1, visible=False)
                self.vlines.append(vline)
        except IndexError:
             print("Aviso: DataFrame vazio ou sem timestamps ao adicionar vlines.")


    def update_plot(self):
        """Roteador para chamar a função de plot correta."""
        if self.df.empty:
            self.figure.clear()
            self.canvas.draw()
            return
            
        if self.radio_voltage.isChecked(): self.plot_voltage()
        elif self.radio_wind_variability.isChecked(): self.plot_wind_variability()
        elif self.radio_rpy.isChecked(): self.plot_rpy()
        elif self.radio_variance.isChecked(): self.plot_variance_rpy_alt()
        elif self.radio_position.isChecked(): self.plot_position()
        else: # Se nenhum estiver checado (caso raro), limpa
             self.figure.clear()
             self.canvas.draw()