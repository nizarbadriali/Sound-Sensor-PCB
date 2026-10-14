clear all; close all; clc;

%% Setup
fprintf('\n');
fprintf('╔══════════════════════════════════════╗\n');
fprintf('║   Sound Sensor Signal-Chain Model    ║\n');
fprintf('║   LM393 comparator (MATLAB)          ║\n');
fprintf('╚══════════════════════════════════════╝\n\n');

% Operating point (edit these)
VCC = 5.0;      % Supply voltage (V), assumed
pot = 0.004;    % RV1 wiper position, 0 (GND end) to 1 (VCC end)

% Nominal component values, read from media/schematic.png
R1  = 2.2e3;    % Microphone bias resistor
R2  = 100e3;    % VCC to GND (see README design observations)
R3  = 100e3;    % U1A + input to GND
R4  = 10e3;     % Output pull-up
R5  = 100e3;    % U1A + input to GND
RV1 = 10e3;     % Sensitivity potentiometer
C1  = 100e-9;   % Coupling capacitor, microphone node to U1A + input

%% Design calculations
r_bias = R3 * R5 / (R3 + R5);
rc     = (R1 + r_bias) * C1;
f_hp   = 1 / (2 * pi * rc);
v_th   = pot * VCC;

fprintf('Design calculations (VCC = %.2f V, RV1 at %.2f %%)\n', VCC, pot * 100);
fprintf('  + input bias (R3 || R5):       %.1f kOhm to GND\n', r_bias / 1e3);
fprintf('  C1 high-pass corner:           %.1f Hz\n', f_hp);
fprintf('  Threshold at - input (RV1):    %.1f mV\n', v_th * 1e3);
fprintf('  Threshold change per 1 %% turn: %.1f mV\n', VCC / 100 * 1e3);
fprintf('  R2 standing current:           %.1f uA\n', VCC / R2 * 1e6);
fprintf('  RV1 divider current:           %.2f mA\n', VCC / RV1 * 1e3);
fprintf('  R4 current, output low:        %.2f mA\n\n', VCC / R4 * 1e3);

% Get list of .dat files in workdir folder
dataFiles = dir('workdir/*.dat');

if isempty(dataFiles)
    fprintf('\033[91m✗ No data files found in workdir/ folder\033[0m\n');
    return;
end

fprintf('\033[92m✓ Found %d data file(s)\033[0m\n\n', length(dataFiles));

%% Process each data file
for fileIdx = 1:length(dataFiles)
    filename = fullfile(dataFiles(fileIdx).folder, dataFiles(fileIdx).name);
    fprintf('\033[94mProcessing:\033[0m %s\n', filename);

    try
        % Load data from file ('#' lines are comments)
        data = readmatrix(filename, 'FileType', 'text', 'CommentStyle', '#');

        if size(data, 2) ~= 2
            fprintf('\033[91m✗ Error: File must have exactly 2 columns (time, voltage)\033[0m\n\n');
            continue;
        end

        t   = data(:, 1);  % Column 1: time (s)
        mic = data(:, 2);  % Column 2: AC signal at MK1 pin 2 (V)
        dt  = mean(diff(t));

        fprintf('  Data points: %d\n', length(t));
        fprintf('  Duration: %.3f s at %.0f Hz\n', t(end) - t(1), 1 / dt);
        fprintf('  Mic signal range: %.1f to %.1f mV\n', min(mic) * 1e3, max(mic) * 1e3);

        v_plus = highPass(mic, dt, rc);
        do_out = comparator(v_plus, v_th, VCC);

        fprintf('  + input range after C1: %.1f to %.1f mV\n', min(v_plus) * 1e3, max(v_plus) * 1e3);
        if min(v_plus) < -0.3
            fprintf('\033[93m  ! + input goes below -0.3 V (LM393 absolute maximum)\033[0m\n');
        end

        high  = do_out > 0;
        edges = sum(high(2:end) & ~high(1:end-1));

        fprintf('\n\033[92m✓ Simulation complete\033[0m\n');
        fprintf('  DO rising edges: %d\n', edges);
        fprintf('  DO high time: %.1f ms (%.1f %% of record)\n\n', sum(high) * dt * 1e3, mean(high) * 100);

        figure('Name', dataFiles(fileIdx).name);
        subplot(2, 1, 1);
        plot(t, v_plus * 1e3); hold on;
        yline(v_th * 1e3, 'r--', 'Threshold');
        ylabel('U1A + input (mV)'); grid on;
        subplot(2, 1, 2);
        plot(t, do_out);
        xlabel('Time (s)'); ylabel('DO (V)'); ylim([-0.5, VCC + 0.5]); grid on;

    catch ME
        fprintf('\033[91m✗ Error processing file: %s\033[0m\n\n', ME.message);
        continue;
    end
end

fprintf('Done!\n\n');


%% ========== LOCAL FUNCTIONS (MUST BE AT VERY BOTTOM) ==========

function y = highPass(x, dt, rc)
    % First-order RC high-pass (C1 into R3 || R5): y[n] = a*(y[n-1] + x[n] - x[n-1])
    a = rc / (rc + dt);
    y = zeros(size(x));
    for i = 2:length(x)
        y(i) = a * (y(i - 1) + x(i) - x(i - 1));
    end
end

function d = comparator(v_plus, v_minus, VCC)
    % Ideal LM393, open-collector output pulled up by R4: high when V+ > V-
    d = VCC * (v_plus > v_minus);
end
