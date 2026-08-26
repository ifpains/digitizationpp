/*
 * Copyright (C) 2026 CYGNO Collaboration
 *
 *
 * Author: Luan Gomes Mattosinhos de Carvalho
 * Created in 2026
 *
 */

#include "PMTHits.h"
#include <cmath>
#include <iostream>

using namespace std;

PhotonPropagation::PhotonPropagation(const vector<double>& x_0,
                                     const vector<double>& y_0,
                                     const vector<int>& n_photons,
                                     const vector<double>& arr_times,
                                     const map<string, string>& options)
    : x_0_(x_0), y_0_(y_0), n_photons_(n_photons), arr_times_(arr_times), options_(options) {
    
    gen.seed(rd());

    r_pmt_sq = std::pow(std::stod(options_.at("pmt_radius")), 2);
    z_pmt_sq = std::pow(std::stod(options_.at("dist_gem_pmt")), 2);
    z_pmt = std::stod(options_.at("dist_gem_pmt"));
    num_pmts = std::stoi(options_.at("pmt_number"));

    for (int i = 1; i <= num_pmts; ++i) {
        string pmt_name = "pmt_" + to_string(i);
        pmt_positions.push_back({std::stod(options_.at(pmt_name + "_x")), 
                                 std::stod(options_.at(pmt_name + "_y"))});
        pmt_names.push_back(pmt_name);
    }
}

map<string, vector<PMTData>> PhotonPropagation::pmt_hits() {
    map<string, vector<PMTData>> all_hits;
    
    for (size_t i = 0; i < x_0_.size(); ++i) {
        const double x = x_0_[i];
        const double y = y_0_[i];
        const int n_pho = n_photons_[i];

        for (int j = 0; j < num_pmts; ++j) {
            const double dx = pmt_positions[j].first - x;
            const double dy = pmt_positions[j].second - y;
            
            const double R2 = dx*dx + dy*dy + z_pmt_sq;
            const double R4 = R2 * R2;

            const double mean = n_pho * r_pmt_sq * z_pmt_sq / (4.0 * R4);
            
            std::poisson_distribution<int> dist(mean);
            
            PMTData data;
            data.hits = dist(gen);
            
            if (data.hits > 0) {
                data.arrival_time = arr_times_[i];
                all_hits[pmt_names[j]].push_back(data);
            }
        }
    }
    return all_hits;
}
